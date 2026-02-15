"""
FastAPI Web UI for the X Automation Agent.
"""
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
from typing import List
from src.agent import Agent
from src.config import Config
from src.database import Database
import threading

app = FastAPI(title="X Automation Agent")
templates = Jinja2Templates(directory="templates")

# Global agent instance
agent = Agent()
db = Database()

# Session status (for async tracking)
session_status = {
    "running": False,
    "progress": "",
    "report": None,
    "progress_log": []
}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main UI page."""
    today_count = db.get_today_reply_count()
    remaining = Config.DAILY_REPLY_LIMIT - today_count
    
    # Load saved prompt or use default
    saved_prompt = db.get_setting("grok_prompt")
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "today_count": today_count,
        "daily_limit": Config.DAILY_REPLY_LIMIT,
        "remaining": remaining,
        "session_status": session_status,
        "saved_prompt": saved_prompt
    })

@app.post("/save_prompt")
async def save_prompt(prompt: str = Form(...)):
    """Save the Grok prompt to the database."""
    db.set_setting("grok_prompt", prompt)
    return JSONResponse({"status": "success", "message": "✅ Prompt saved successfully!"})

@app.post("/run")
async def run_automation(
    post_urls: str = Form(...),
    target_count: int = Form(None)
):
    """Run the automation with given post URLs and optional target count."""
    global session_status
    
    # If no target count provided, default to a high number to process all provided
    if target_count is None:
        target_count = 999
    
    if session_status["running"]:
        return JSONResponse({
            "status": "error",
            "message": "Session already running!"
        })
    
    # --- ROBUST PARSER ---
    # Split text into blocks by URL, but KEEP the URLs for context
    # This regex finds URLs
    link_pattern = r'(https?://(?:twitter|x)\.com/[^/ \n\r\t]+(?:/status/\d+)?(?:(?:\?|#)\S+)?|https?://t\.co/\S+)'
    
    # Split by link but keep the links in the result
    parts = re.split(f"({link_pattern})", post_urls)
    
    session_data = []
    # parts will look like: [text_before_url1, url1, text_between_1_and_2, url2, ...]
    for i in range(1, len(parts), 2):
        url = parts[i].strip()
        # Text could be before OR after. 
        # Usually Grok gives: "Some text https://x.com/..." OR "https://x.com/... ne post kiya: some text"
        text_before = parts[i-1].strip()
        text_after = parts[i+1].strip() if i+1 < len(parts) else ""
        
        # Heuristic: Combine them and clean up "ne post kiya:" garbage
        combined_context = f"{text_before}\n{text_after}".strip()
        # Clean common "Grokisms"
        combined_context = re.sub(r'(?:ne )?post (?:kiya|ha?i):?\s*', '', combined_context, flags=re.IGNORECASE)
        combined_context = combined_context.strip().strip('"').strip("'")
        
        session_data.append({'url': url, 'content': combined_context})
    
    if not session_data:
        return JSONResponse({
            "status": "error",
            "message": "No valid X/Twitter URLs found in the text!"
        })
    
    # Run in background thread
    def run_in_background():
        global session_status
        session_status["running"] = True
        session_status["progress"] = "Starting..."
        session_status["progress_log"] = []
        
        def progress_callback(msg):
            session_status["progress_log"].append(msg)
            session_status["progress"] = msg
        
        try:
            report = agent.run_session(session_data, target_count, progress_callback)

            session_status["report"] = report
            if report.get("status") == "stopped":
                session_status["progress"] = "🛑 Stopped by user"
            else:
                session_status["progress"] = "Completed!"
        except Exception as e:
            session_status["report"] = {
                "status": "error",
                "message": str(e)
            }
            session_status["progress_log"].append(f"❌ Error: {str(e)}")
        finally:
            session_status["running"] = False
    
    thread = threading.Thread(target=run_in_background)
    thread.start()
    
    return JSONResponse({
        "status": "success",
        "message": "Session started! Check /status for updates."
    })

@app.get("/status")
async def get_status():
    """Get current session status."""
    return JSONResponse(session_status)

@app.get("/history")
async def get_history():
    """Get reply history for the last 3 days."""
    history = db.get_history(days=3)
    return JSONResponse(history)

@app.post("/stop")
async def stop_automation():
    """Stop the running automation session."""
    global agent
    if session_status["running"]:
        agent.stop_requested = True
        return JSONResponse({
            "status": "success",
            "message": "🛑 Stop signal sent. Bot will wrap up in 1-2 seconds."
        })
    else:
        return JSONResponse({
            "status": "error",
            "message": "No session is currently running."
        })

if __name__ == "__main__":
    import os
    print("🚀 Starting X Automation Agent...")
    
    try:
        Config.validate()
        print("✅ Configuration validated.")
    except Exception as e:
        print(f"⚠️ Configuration Warning: {e}")
        print("Application will start but might fail during automation runs.")
        
    try:
        db.cleanup_old_data(days=3)
        print("✅ Database cleanup completed.")
    except Exception as e:
        print(f"⚠️ Database Error: {e}")

    port = int(os.environ.get("PORT", 8000))
    print(f"📡 Listening on port: {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)
