"""
LLM Client for generating human-style replies using OpenAI.
"""
from openai import OpenAI
from .config import Config
from typing import List
import difflib

class LLMClient:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.system_prompt = """You are a helpful Twitter user who writes thoughtful, natural replies.

Rules:
- Write 1-3 short sentences maximum
- Keep under 220 characters
- Use simple, conversational English
- NO emojis
- NO quotation marks
- NO long dashes (—)
- NO generic praise like "Great post!" or "Amazing!"
- Add one useful insight, question, or thoughtful comment
- Vary sentence structure
- Sound like a real human, not a bot"""
    
    def generate_reply(self, tweet_text: str, previous_replies: List[str] = None) -> str:
        """Generate a reply for the given tweet."""
        user_prompt = f"""Write a brief, thoughtful reply to this tweet:

"{tweet_text}"

Remember: Under 220 chars, no emoji, sound natural and human."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.9  # High temp for variety
            )
            
            reply = response.choices[0].message.content.strip()
            
            # Remove any accidental quotes
            reply = reply.strip('"').strip("'")
            
            # Check length
            if len(reply) > 220:
                reply = reply[:217] + "..."
            
            return reply
        except Exception as e:
            print(f"Error generating reply: {e}")
            return None
    
    def is_too_similar(self, new_reply: str, previous_replies: List[str], threshold: float = 0.6) -> bool:
        """Check if the new reply is too similar to previous ones."""
        if not previous_replies:
            return False
        
        for prev in previous_replies:
            similarity = difflib.SequenceMatcher(None, new_reply.lower(), prev.lower()).ratio()
            if similarity > threshold:
                return True
        
        return False
    
    def generate_unique_reply(self, tweet_text: str, previous_replies: List[str], max_attempts: int = 3) -> str:
        """Generate a reply that's not too similar to previous ones."""
        for attempt in range(max_attempts):
            reply = self.generate_reply(tweet_text, previous_replies)
            if not reply:
                return None
            
            if not self.is_too_similar(reply, previous_replies):
                return reply
        
        # If all attempts failed, return the last one anyway
        return reply
