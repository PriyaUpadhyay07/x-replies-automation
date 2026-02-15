"""
Database module for tracking processed posts and daily statistics.
"""
import sqlite3
from datetime import datetime, date
from typing import List, Optional
import os

class Database:
    def __init__(self, db_path: str = "automation.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table for processed posts (Detailed History)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_url TEXT UNIQUE NOT NULL,
                post_id TEXT NOT NULL,
                reply_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table for daily statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date DATE PRIMARY KEY,
                reply_count INTEGER DEFAULT 0
            )
        """)
        
        # Table for today's posted replies (for similarity check)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todays_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reply_text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table for generic settings (persistent config)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a persistent setting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Save or update a persistent setting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()

    def is_post_processed(self, post_url: str) -> bool:
        """Check if a post has already been replied to."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_posts WHERE post_url = ?", (post_url,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def mark_post_processed(self, post_url: str, post_id: str, reply_text: str = None):
        """Mark a post as processed with reply text."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Check if columns exist (for migration)
            cursor.execute("PRAGMA table_info(processed_posts)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'reply_text' not in columns:
                cursor.execute("ALTER TABLE processed_posts ADD COLUMN reply_text TEXT")
            
            cursor.execute(
                "INSERT INTO processed_posts (post_url, post_id, reply_text) VALUES (?, ?, ?)",
                (post_url, post_id, reply_text)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already exists
        finally:
            conn.close()
    
    def get_history(self, days: int = 3) -> List[dict]:
        """Fetch reply history for the last X days."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT post_url, reply_text, timestamp 
            FROM processed_posts 
            WHERE timestamp >= datetime('now', ?) 
            ORDER BY timestamp DESC
        """, (f'-{days} days',))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def cleanup_old_data(self, days: int = 3):
        """Delete data older than X days to keep DB smooth."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Clean processed posts history
        cursor.execute("DELETE FROM processed_posts WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        # Clean daily stats (keep a bit longer, maybe 7 days, but user asked for 1-3)
        cursor.execute("DELETE FROM daily_stats WHERE date < date('now', ?)", (f'-{days} days',))
        # Todays replies is already cleaned daily
        cursor.execute("DELETE FROM todays_replies WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        conn.commit()
        conn.close()

    def get_today_reply_count(self) -> int:
        """Get the number of replies posted today."""
        today = date.today()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT reply_count FROM daily_stats WHERE date = ?", (today,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    
    def increment_daily_count(self):
        """Increment today's reply count."""
        today = date.today()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO daily_stats (date, reply_count) VALUES (?, 1) ON CONFLICT(date) DO UPDATE SET reply_count = reply_count + 1",
            (today,)
        )
        conn.commit()
        conn.close()
    
    def save_todays_reply(self, reply_text: str):
        """Save a reply to today's replies for similarity checking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO todays_replies (reply_text) VALUES (?)", (reply_text,))
        conn.commit()
        conn.close()
    
    def get_todays_replies(self) -> List[str]:
        """Get all replies posted today."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT reply_text FROM todays_replies WHERE DATE(timestamp) = DATE('now')")
        results = cursor.fetchall()
        conn.close()
        return [r[0] for r in results]
    
    def clear_old_daily_replies(self):
        """Clear replies older than today (run at startup)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM todays_replies WHERE DATE(timestamp) < DATE('now')")
        conn.commit()
        conn.close()
