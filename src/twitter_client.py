"""
Twitter/X API Client wrapper using Tweepy.
Now with auto-retry, detailed error reporting, and self-healing.
"""
import tweepy
from typing import Optional, Dict, Tuple
import re
import time
from .config import Config


class TwitterClient:
    def __init__(self):
        self._init_client()
        self.MAX_RETRIES = 3
        self.RATE_LIMIT_RETRIES = 2  # Extra retries for rate limits
        self.RETRY_DELAYS = [5, 15, 30]  # Exponential backoff (seconds)
        self.rate_limited_until = 0  # Timestamp when rate limit expires

    def _init_client(self):
        """Initialize or re-initialize the Tweepy client (self-healing reconnect)."""
        self.client = tweepy.Client(
            consumer_key=Config.X_API_KEY,
            consumer_secret=Config.X_API_KEY_SECRET,
            access_token=Config.X_ACCESS_TOKEN,
            access_token_secret=Config.X_ACCESS_TOKEN_SECRET
        )

    def _classify_error(self, error: Exception) -> Dict:
        """Classify an error as retryable or permanent, with details."""
        error_str = str(error).lower()
        
        # Rate limit errors — RETRYABLE (wait longer)
        if "429" in str(error) or "rate limit" in error_str or "too many" in error_str:
            return {
                "retryable": True,
                "category": "rate_limit",
                "message": f"Rate limited by Twitter.",
                "wait_time": 180  # Wait 3 minutes on rate limit, then retry
            }
        
        # Server errors (500, 502, 503, 504) — RETRYABLE
        if any(code in str(error) for code in ["500", "502", "503", "504"]):
            return {
                "retryable": True,
                "category": "server_error",
                "message": f"Twitter server error. Will auto-retry.",
                "wait_time": 10
            }
        
        # Network / connection errors — RETRYABLE
        if any(kw in error_str for kw in ["connection", "timeout", "network", "reset", "broken pipe"]):
            return {
                "retryable": True,
                "category": "network",
                "message": f"Network error. Will auto-retry.",
                "wait_time": 5
            }
        
        # Auth errors (401, 403) — TRY RECONNECT once, then permanent
        if "401" in str(error) or "unauthorized" in error_str:
            return {
                "retryable": True,  # Try reconnecting the client once
                "category": "auth",
                "message": f"Auth error (401). Attempting reconnect.",
                "wait_time": 2,
                "reconnect": True
            }
        
        if "403" in str(error) or "forbidden" in error_str:
            return {
                "retryable": False,
                "category": "forbidden",
                "message": f"Forbidden (403): {str(error)[:150]}. Check API permissions.",
                "wait_time": 0
            }
        
        # Duplicate tweet error — SKIP (not retryable but not really an error)
        if "duplicate" in error_str or "already" in error_str:
            return {
                "retryable": False,
                "category": "duplicate",
                "message": "Duplicate tweet — already posted.",
                "wait_time": 0
            }
        
        # Unknown errors — retry once
        return {
            "retryable": True,
            "category": "unknown",
            "message": f"Unknown error: {str(error)[:200]}",
            "wait_time": 5
        }

    def extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from a Twitter/X URL."""
        pattern = r'(?:twitter|x)\.com/[^/]+/status/(\d+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None

    def get_tweet(self, tweet_id: str) -> Optional[Dict]:
        """Fetch tweet details with auto-retry."""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.get_tweet(
                    id=tweet_id,
                    tweet_fields=['author_id', 'created_at', 'text']
                )
                if response.data:
                    return {
                        'data': response.data,
                        'text': response.data.text if hasattr(response.data, 'text') else None
                    }
                return None
            except Exception as e:
                last_error = e
                err_info = self._classify_error(e)
                print(f"[Retry {attempt+1}/{self.MAX_RETRIES}] get_tweet error: {err_info['message']}")
                
                if err_info.get("reconnect"):
                    print("  -> Reconnecting Twitter client...")
                    self._init_client()
                
                if not err_info["retryable"] or attempt == self.MAX_RETRIES - 1:
                    break
                
                time.sleep(err_info["wait_time"])
        
        print(f"get_tweet failed after {self.MAX_RETRIES} attempts: {last_error}")
        return None

    def is_rate_limited(self) -> bool:
        """Check if we're currently in a rate limit cooldown."""
        return time.time() < self.rate_limited_until

    def get_rate_limit_remaining(self) -> int:
        """Get seconds remaining in rate limit cooldown."""
        remaining = self.rate_limited_until - time.time()
        return max(0, int(remaining))

    def post_reply(self, tweet_id: str, reply_text: str, log_func=None) -> Tuple[bool, str]:
        """
        Post a reply with auto-retry and detailed error reporting.
        Returns (success: bool, error_detail: str).
        On success, error_detail is empty.
        log_func: optional callback to send progress to UI.
        """
        def log(msg):
            if log_func:
                log_func(msg)
            print(msg)

        # If we're in a rate limit cooldown, wait it out first
        if self.is_rate_limited():
            wait_secs = self.get_rate_limit_remaining()
            log(f"   ⏸️ Rate limit active. Waiting {wait_secs//60}m {wait_secs%60}s...")
            time.sleep(wait_secs)

        last_error_msg = ""
        reconnected = False
        max_retries = self.MAX_RETRIES
        
        for attempt in range(max_retries):
            try:
                response = self.client.create_tweet(
                    text=reply_text,
                    in_reply_to_tweet_id=tweet_id
                )
                if response.data is not None:
                    self.rate_limited_until = 0  # Reset on success
                    return (True, "")
                else:
                    last_error_msg = "API returned empty response"
            except Exception as e:
                err_info = self._classify_error(e)
                last_error_msg = err_info["message"]
                log(f"   ⚠️ Attempt {attempt+1}/{max_retries}: {last_error_msg}")
                
                # Self-healing: reconnect on auth errors (once)
                if err_info.get("reconnect") and not reconnected:
                    log("   🔄 Reconnecting Twitter client...")
                    self._init_client()
                    reconnected = True
                
                # Rate limit: set cooldown and do longer wait
                if err_info["category"] == "rate_limit":
                    self.rate_limited_until = time.time() + err_info["wait_time"]
                    if attempt < max_retries - 1:
                        wait_min = err_info["wait_time"] // 60
                        log(f"   ⏸️ Rate limited. Cooling down for {wait_min} minutes...")
                        time.sleep(err_info["wait_time"])
                        continue
                
                if not err_info["retryable"] or attempt == max_retries - 1:
                    break
                
                wait = err_info["wait_time"]
                log(f"   ⏳ Waiting {wait}s before retry...")
                time.sleep(wait)
        
        return (False, last_error_msg)
