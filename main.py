"""
FastAPI Web UI for the X Automation Agent.
"""
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn
from typing import List
import re
import traceback
from src.agent import Agent
from src.config import Config
from src.database import Database
import threading

app = FastAPI(title="X Automation Agent")
templates = Jinja2Templates(directory="templates")

# ============================================================
# GLOBAL ERROR HANDLER — ensures ALL errors return valid JSON
# ============================================================
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        {"status": "error", "message": str(exc.detail)},
        status_code=exc.status_code
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    traceback.print_exc()
    return JSONResponse(
        {"status": "error", "message": f"Internal server error: {str(exc)}"},
        status_code=500
    )

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

DEFAULT_GROK_PROMPT = """mujhe in account se post do (post link + text version of post). 
jo abhi abhi 1 hour m post ki gyi ho. 

@marclou
@UiSavior
@Davidjpark96
@tibo_maker
@levelsio
@codyschneiderxx
@iamfra5er
@yasser_elsaid_
@nickbakeddesign
@devbasu
@JaredSleeper
@kalashbuilds
@uxchrisnguyen
@IslamRashi2000
@om_patel5
@KalyfaMuhd
@xeeliz
@AngelinaUXN
@musa_pyuza
@newincreative
@alexhaagaard
@jeggers
@tessalau
@petecodes
@JensLennartsson
@aazarshad
@nocodelife
@AlexWestCo
@AlexHaagaard
@AngelList
@BenTossell
@ChrisNguyenUX
@ChrisOlson
@CodexCoder
@DannyPostmaa
@DevBasu
@DougCollinsUX
@Ellevenio
@EthanGarr
@Gavofyork
@Hnshah
@Housecor
@Imoyse
@JanuBuilds
@Jasonfried
@Jh3yy
@Johncutlefish
@Justcreative
@Levelsio
@Lisadziuba
@Mlane
@Newincreative
@OllyMeakings
@PatmMatthews
@Petecodes
@PieterLevels
@RachelAndrew
@Sarasoueidan
@SeanEllis
@Stucollett
@VadimNotJustDev
@Wojtekim
@Yongfook"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main UI page."""
    today_count = db.get_today_reply_count()
    remaining = Config.DAILY_REPLY_LIMIT - today_count
    
    # Load saved prompt or use default
    saved_prompt = db.get_setting("grok_prompt", DEFAULT_GROK_PROMPT)
    
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
    """Save the Grok prompt to the database, sanitizing it for HTML safety."""
    try:
        clean_prompt = prompt.replace("</textarea>", "").replace("<textarea>", "")
        db.set_setting("grok_prompt", clean_prompt)
        return JSONResponse({"status": "success", "message": "✅ Prompt saved successfully!"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Save failed: {str(e)}"}, status_code=500)

@app.post("/reset_prompt")
async def reset_prompt():
    """Reset the Grok prompt to the default."""
    try:
        db.set_setting("grok_prompt", DEFAULT_GROK_PROMPT)
        return JSONResponse({"status": "success", "message": "✅ Prompt reset to default!"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Reset failed: {str(e)}"}, status_code=500)

@app.post("/run")
async def run_automation(
    post_urls: str = Form(...),
    target_count: int = Form(None)
):
    """Run the automation with given post URLs and optional target count."""
    global session_status
    
    try:
        # If no target count provided, default to a high number to process all provided
        if target_count is None:
            target_count = 999
        
        if session_status["running"]:
            return JSONResponse({
                "status": "error",
                "message": "Session already running!"
            })
        
        # --- ROBUST PARSER ---
        # Use findall to extract all URLs first
        link_pattern = r'https?://(?:twitter|x)\.com/[^ \n\r\t]+(?:/status/\d+)?(?:(?:\?|#)\S+)?|https?://t\.co/\S+'
        
        # Find all URLs
        urls_found = re.findall(link_pattern, post_urls)
        
        if not urls_found:
            return JSONResponse({
                "status": "error",
                "message": "No valid X/Twitter URLs found in the text!"
            })
        
        # Split by URLs to get surrounding text
        text_parts = re.split(link_pattern, post_urls)
        
        session_data = []
        for idx, url in enumerate(urls_found):
            url = url.strip()
            # Text before this URL
            text_before = text_parts[idx].strip() if idx < len(text_parts) else ""
            # Text after this URL  
            text_after = text_parts[idx + 1].strip() if idx + 1 < len(text_parts) else ""
            
            # Combine and clean
            combined_context = f"{text_before}\n{text_after}".strip()
            # Clean common "Grokisms"
            combined_context = re.sub(r'(?:ne )?post (?:kiya|ha?i):?\s*', '', combined_context, flags=re.IGNORECASE)
            combined_context = combined_context.strip().strip('"').strip("'")
            
            session_data.append({'url': url, 'content': combined_context})
        
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
    except Exception as e:
        # Catch-all: ALWAYS return valid JSON, never a raw 500
        return JSONResponse(
            {"status": "error", "message": f"Server error: {str(e)}"},
            status_code=500
        )

@app.get("/status")
async def get_status():
    """Get current session status."""
    try:
        return JSONResponse(session_status)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/history")
async def get_history():
    """Get reply history for the last 3 days."""
    try:
        history = db.get_history(days=3)
        return JSONResponse(history)
    except Exception as e:
        return JSONResponse([], status_code=200)  # Return empty list on error

@app.post("/stop")
async def stop_automation():
    """Stop the running automation session."""
    try:
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
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/health")
async def health_check():
    """Health check endpoint — verifies all components are alive."""
    health = {"status": "ok", "checks": {}}
    try:
        db.get_today_reply_count()
        health["checks"]["database"] = "ok"
    except Exception as e:
        health["checks"]["database"] = f"error: {str(e)}"
        health["status"] = "degraded"
    try:
        _ = Config.DAILY_REPLY_LIMIT
        health["checks"]["config"] = "ok"
    except Exception as e:
        health["checks"]["config"] = f"error: {str(e)}"
        health["status"] = "degraded"
    health["checks"]["agent"] = "ok" if agent else "error: not initialized"
    return JSONResponse(health)

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
