"""
Main Agent - Orchestrates the entire reply automation workflow.
"""
import time
import random
from datetime import datetime
from typing import List, Dict
from .database import Database
from .twitter_client import TwitterClient
from .llm_client import LLMClient
from .config import Config

class Agent:
    def interruptible_sleep(self, seconds, log_func=None):
        """Sleep in small increments to remain responsive to stop requests."""
        for _ in range(int(seconds)):
            if self.stop_requested:
                return True
            time.sleep(1)
        return False

    def run_session(self, session_data: List[Dict], target_count: int, progress_callback=None) -> Dict:
        """
        Run a reply session for the given data (URL + optional content).
        Returns a report of the session.
        session_data: List of dicts like {'url': '...', 'content': '...'}
        """
        self.stop_requested = False  # Reset stop flag
        self.session_start_time = datetime.now()
        
        def log_progress(msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            timestamped_msg = f"[{timestamp}] {msg}"
            if progress_callback:
                progress_callback(timestamped_msg)
            print(timestamped_msg)
        
        # Check daily limit
        today_count = self.db.get_today_reply_count()
        remaining = Config.DAILY_REPLY_LIMIT - today_count
        
        log_progress(f"📊 Daily Status: {today_count}/{Config.DAILY_REPLY_LIMIT} replies used, {remaining} remaining")
        
        if remaining <= 0:
            return {
                "status": "error",
                "message": f"Daily limit ({Config.DAILY_REPLY_LIMIT}) already reached!",
                "total_replies": 0,
                "skipped": 0,
                "failed": 0
            }
        
        # Adjust target if needed
        actual_target = min(target_count, remaining, len(session_data))
        log_progress(f"🎯 Target: {actual_target} replies from {len(session_data)} items provided")
        
        report = {
            "status": "running",
            "total_replies": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "success_posts": [],
            "progress_log": [],
            "stopped_by_user": False
        }
        
        processed = 0
        batch_count = 0
        
        for i, item in enumerate(session_data):
            url = item['url']
            provided_content = item.get('content', '')

            # Check if stop was requested
            if self.stop_requested:
                log_progress(f"🛑 Stop requested by user. Stopping session.")
                report["stopped_by_user"] = True
                break
            
            if processed >= actual_target:
                log_progress(f"✅ Target reached! Stopping.")
                break
            
            log_progress(f"\n--- Processing {i+1}/{len(session_data)} ---")
            log_progress(f"🔗 URL: {url[:60]}...")
            
            # Batch break logic
            if batch_count > 0 and batch_count % Config.BATCH_SIZE == 0:
                break_time = random.randint(Config.BATCH_BREAK_MIN, Config.BATCH_BREAK_MAX)
                log_progress(f"☕ Batch break: Waiting {break_time//60} minutes...")
                if self.interruptible_sleep(break_time):
                    log_progress("🛑 Stop requested during batch break.")
                    report["stopped_by_user"] = True
                    break
            
            # Process single post
            result = self._process_single_post(url, provided_content, log_progress)
            
            if result["status"] == "success":
                report["total_replies"] += 1
                report["success_posts"].append(url)
                processed += 1
                batch_count += 1
                
                log_progress(f"✅ Success! ({processed}/{actual_target} completed)")
                
                # Human delay between replies
                if processed < actual_target:
                    delay = random.randint(Config.REPLY_DELAY_MIN, Config.REPLY_DELAY_MAX)
                    log_progress(f"⏳ Human delay: {delay} seconds...")
                    if self.interruptible_sleep(delay):
                        log_progress("🛑 Stop requested during delay.")
                        report["stopped_by_user"] = True
                        break
            
            elif result["status"] == "skipped":
                report["skipped"] += 1
                log_progress(f"⏭️ Skipped: {result.get('reason', 'Unknown')}")
            else:
                report["failed"] += 1
                report["errors"].append(f"{url}: {result.get('error', 'Unknown error')}")
                log_progress(f"❌ Failed: {result.get('error', 'Unknown')}")
        
        if report["stopped_by_user"]:
            log_progress(f"\n🛑 Session stopped by user.")
            report["status"] = "stopped"
        else:
            log_progress(f"\n🎉 Session Complete!")
            report["status"] = "completed"

        log_progress(f"📈 Posted: {report['total_replies']}, Skipped: {report['skipped']}, Failed: {report['failed']}")
        return report
    
    def _process_single_post(self, url: str, provided_text: str = None, logger=None) -> Dict:
        """Process a single post: extract ID, generate reply, post it."""
        
        def log(msg):
            if logger:
                logger(msg)
            print(msg)
        
        # Check if already processed
        if self.db.is_post_processed(url):
            log(f"⏭️ Already replied to this post")
            return {"status": "skipped", "reason": "already_processed"}
        
        # Extract tweet ID
        tweet_id = self.twitter.extract_tweet_id(url)
        if not tweet_id:
            log(f"❌ Invalid URL format")
            return {"status": "failed", "error": "Invalid URL"}
        
        tweet_text = ""
        
        if provided_text and len(provided_text.strip()) > 5:
            log(f"📝 Using provided text (Bypassing API fetch)")
            tweet_text = provided_text
        else:
            # Fetch tweet text (MANDATORY - skip if can't read)
            log(f"🔍 Fetching tweet content from API...")
            tweet_data = self.twitter.get_tweet(tweet_id)
            
            if not tweet_data or not tweet_data.get('text'):
                log(f"⚠️ Cannot read tweet content (API limitation)")
                log(f"💡 SKIP: Need text content to generate quality reply")
                return {"status": "skipped", "reason": "cannot_read_tweet_text"}
            tweet_text = tweet_data['text']
        
        log(f"📝 Content: {tweet_text[:100]}...")
        
        # Validate tweet has meaningful content
        if len(tweet_text.strip()) < 5:
            log(f"⚠️ Content too short or empty")
            return {"status": "skipped", "reason": "content_too_short"}
        
        # Generate reply
        previous_replies = self.db.get_todays_replies()
        log(f"🤖 Generating reply...")
        reply_text = self.llm.generate_unique_reply(tweet_text, previous_replies)
        
        if not reply_text:
            log(f"❌ Failed to generate reply")
            return {"status": "failed", "error": "LLM generation failed"}
        
        log(f"💬 Reply: \"{reply_text}\"")
        
        # Post reply
        log(f"📤 Posting...")
        success = self.twitter.post_reply(tweet_id, reply_text)
        
        if success:
            # Save to database
            self.db.mark_post_processed(url, tweet_id, reply_text)
            self.db.increment_daily_count()
            self.db.save_todays_reply(reply_text)
            log(f"✅ Posted successfully!")
            return {"status": "success", "reply": reply_text}
        else:
            log(f"❌ Failed to post")
            return {"status": "failed", "error": "Twitter API error"}
