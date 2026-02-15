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
        self.RETRY_DELAYS = [5, 15, 30]  # Exponential backoff (seconds)

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
        
        # Rate limit errors — RETRYABLE (wait and try again)
        if "429" in str(error) or "rate limit" in error_str or "too many" in error_str:
            return {
                "retryable": True,
                "category": "rate_limit",
                "message": f"Rate limited by Twitter. Will auto-retry.",
                "wait_time": 60  # Wait 1 minute on rate limit
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

    def post_reply(self, tweet_id: str, reply_text: str) -> Tuple[bool, str]:
        """
        Post a reply with auto-retry and detailed error reporting.
        Returns (success: bool, error_detail: str).
        On success, error_detail is empty.
        """
        last_error_msg = ""
        reconnected = False
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.create_tweet(
                    text=reply_text,
                    in_reply_to_tweet_id=tweet_id
                )
                if response.data is not None:
                    return (True, "")
                else:
                    last_error_msg = "API returned empty response"
            except Exception as e:
                err_info = self._classify_error(e)
                last_error_msg = err_info["message"]
                print(f"[Retry {attempt+1}/{self.MAX_RETRIES}] post_reply error: {last_error_msg}")
                
                # Self-healing: reconnect on auth errors (once)
                if err_info.get("reconnect") and not reconnected:
                    print("  -> Reconnecting Twitter client...")
                    self._init_client()
                    reconnected = True
                
                if not err_info["retryable"] or attempt == self.MAX_RETRIES - 1:
                    break
                
                wait = err_info["wait_time"]
                print(f"  -> Waiting {wait}s before retry...")
                time.sleep(wait)
        
        return (False, last_error_msg)
