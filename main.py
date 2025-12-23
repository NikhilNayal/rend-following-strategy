
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from typing import Dict, Any
from dotenv import load_dotenv

# Load secret passwords from the .env file (like database password)
load_dotenv()

from strategy_engine import StrategyEngine
from config_manager import ConfigManager
from contextlib import asynccontextmanager

# Configure logging to be quiet. 
# "uvicorn.access" talks too much about every click on the website. We hide that.
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# --- STARTUP & SHUTDOWN ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    This function runs when the server starts and stops.
    It's like the "On" button and "Off" button logic.
    """
    # 1. Startup Logic
    print("\n" + "="*60)
    print("🚀 TREND FOLLOWING STRATEGY - STARTING")
    print("="*60 + "\n")

    # Read start time from config for display
    try:
        settings = await config_manager.get_strategy_settings()
        start_time = settings["time_range"]["start"]
        print(f"⏰ Waiting for {start_time} to start trading...")
    except:
        print("⏰ Waiting for start time (check config)...")
    
    # Run the Strategy Engine in the background!
    # "create_task" puts it on a separate background thread so it doesn't block the website.
    asyncio.create_task(strategy_engine.start())
    
    yield # The app runs while we are paused here...
    
    # 2. Shutdown Logic
    print("\n" + "="*60)
    print("🛑 STRATEGY STOPPED")
    print("="*60 + "\n")

# Create the Web Application
app = FastAPI(title="Trend Following Strategy", lifespan=lifespan)

# --- SECURITY (CORS) ---
# Allow anyone to talk to this API (since we run it locally).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize our Robot Brain (StrategyEngine) and Instruction Manual (ConfigManager)
strategy_engine = StrategyEngine()
config_manager = ConfigManager()

# --- API ENDPOINTS (The URL Commands) ---
# When the Dashboard asks questions, these function answer.

@app.get("/health")
async def health_check():
    """
    Q: "Are you alive?"
    A: "OK"
    """
    return {"status": "ok"}

@app.get("/config")
async def get_config():
    """
    Q: "What are the current settings?"
    """
    return await config_manager.get_config()

@app.post("/config")
async def update_config(config: Dict[str, Any]):
    """
    Q: "I want to change the settings!"
    
    Rule: You CANNOT change settings if the car is moving (is_running = True)!
    """
    current_config = await config_manager.get_config()
    if current_config["is_running"]:
        raise HTTPException(status_code=400, detail="Cannot update config while strategy is running")
    
    await config_manager.update_config(config)
    return {"message": "Config updated"}

@app.get("/status")
async def get_status():
    """
    Q: "What is happening right now? Show me everything."
    
    This is the main function the Dashboard calls every second to update the boxes.
    """
    # Return BOTH the Settings (Config) AND the Robot Brain Memory (Strategy State)
    config = await config_manager.get_config()
    return {
        "config": config,
        "strategy_state": strategy_engine.state
    }

@app.post("/control/start")
async def start_strategy():
    """
    Button: [START STRATEGY]
    """
    await config_manager.set_is_running(True)
    return {"message": "Strategy Started"}

@app.post("/control/stop")
async def stop_strategy():
    """
    Button: [STOP STRATEGY]
    """
    await config_manager.set_is_running(False)
    return {"message": "Strategy Stopped"}

@app.get("/spot_price")
async def get_spot_price(instrument: str = None):
    """
    Q: "What is the price of BANKNIFTY right now?"
    Used for the header on the dashboard.
    """
    try:
        # Check config if no instrument provided
        if not instrument:
            settings = await config_manager.get_strategy_settings()
            instrument = settings["instrument"]
        # Ensure database is connected (if not already)
        if not strategy_engine.db.pool:
            await strategy_engine.db.connect()
        
        spot_price = await strategy_engine.db.get_latest_spot_price(instrument)
        return {"spot_price": spot_price, "instrument": instrument}
    except Exception as e:
        return {"spot_price": None, "error": str(e)}

# --- WEBSITE SERVING ---
# This tells the server to serve the "web" folder (index.html, styles.css, etc.)
# So when you go to http://localhost:8000, you see the pretty dashboard.
app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print("📊 Dashboard: http://localhost:8000")
    print("="*60 + "\n")
    
    # Start the Web Server!
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="warning"  # Suppress INFO logs from uvicorn so terminal stays clean
    )

