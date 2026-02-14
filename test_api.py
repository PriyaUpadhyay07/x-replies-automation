import os
import tweepy
from dotenv import load_dotenv

def test_x_api():
    load_dotenv()
    
    # Load credentials
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_KEY_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
    
    print("--- X API Test ---")
    try:
        # Authenticate with V2 client
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        
        # Try to get own user info (This is a Read action, might be restricted on Free Tier)
        # Instead, let's try a simple "id" check which is usually allowed for auth test
        me = client.get_me()
        if me.data:
            print(f"✅ Success! Connected as: @{me.data.username}")
        else:
            print("⚠️ Connected, but couldn't fetch user data.")
            
    except Exception as e:
        print(f"❌ Failed: {str(e)}")

if __name__ == "__main__":
    test_x_api()
