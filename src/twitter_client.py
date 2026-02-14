"""
Twitter/X API Client wrapper using Tweepy.
"""
import tweepy
from typing import Optional
import re
from .config import Config

class TwitterClient:
    def __init__(self):
        self.client = tweepy.Client(
            consumer_key=Config.X_API_KEY,
            consumer_secret=Config.X_API_KEY_SECRET,
            access_token=Config.X_ACCESS_TOKEN,
            access_token_secret=Config.X_ACCESS_TOKEN_SECRET
        )
    
    def extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from a Twitter/X URL."""
        # Pattern: https://twitter.com/username/status/1234567890
        # or: https://x.com/username/status/1234567890
        pattern = r'(?:twitter|x)\.com/[^/]+/status/(\d+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    
    def get_tweet(self, tweet_id: str):
        """Fetch tweet details and text."""
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
            print(f"Error fetching tweet {tweet_id}: {e}")
            return None
    
    def post_reply(self, tweet_id: str, reply_text: str) -> bool:
        """Post a reply to a tweet."""
        try:
            response = self.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id
            )
            return response.data is not None
        except Exception as e:
            print(f"Error posting reply: {e}")
            return False
