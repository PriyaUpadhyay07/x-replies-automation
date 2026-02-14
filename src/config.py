"""
Configuration loader from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # X API Credentials
    X_API_KEY = os.getenv("X_API_KEY")
    X_API_KEY_SECRET = os.getenv("X_API_KEY_SECRET")
    X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
    X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
    X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
    
    # OpenAI API
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # App Settings
    DAILY_REPLY_LIMIT = int(os.getenv("DAILY_REPLY_LIMIT", 50))
    REPLY_DELAY_MIN = int(os.getenv("REPLY_DELAY_MIN", 60))
    REPLY_DELAY_MAX = int(os.getenv("REPLY_DELAY_MAX", 180))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))
    BATCH_BREAK_MIN = int(os.getenv("BATCH_BREAK_MIN", 600))  # 10 minutes
    BATCH_BREAK_MAX = int(os.getenv("BATCH_BREAK_MAX", 900))  # 15 minutes
    
    @classmethod
    def validate(cls):
        """Validate that all required configs are set."""
        required = [
            "X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", 
            "X_ACCESS_TOKEN_SECRET", "OPENAI_API_KEY"
        ]
        missing = [key for key in required if not getattr(cls, key)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
