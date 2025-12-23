import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
import sys
import os
from datetime import datetime, timedelta

# Setup Logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestVerifier")

# Mock imports BEFORE strategy_engine import if possible, 
# but strategy_engine imports them at top level. 
# We will use sys.modules to mock them before importing strategy_engine.

sys.modules["db_client"] = MagicMock()
sys.modules["angel_client"] = MagicMock()
sys.modules["config_manager"] = MagicMock()

# Define Mock Classes
class MockDB:
    async def connect(self): pass
    async def get_active_expiries(self, inst): return ["26JAN"]
    async def get_latest_spot_price(self, inst): return 59100.0
    async def get_token_for_strike(self, *args): return 12345
    async def get_option_price(self, token): return 200.0
    async def get_available_strikes(self, *args): 
        # Return a list of dicts as expected
        return [
            {"strike_price": 59100, "last_price": 200.0, "instrument_token": 12345, "tradingsymbol": "BANKNIFTY26JAN59100CE", "expiry": "26JAN"}
        ]
    async def get_range_high_low(self, *args): return {"high": 250.0, "low": 150.0}

class MockAngel:
    def login(self): pass
    def place_order(self, *args): return "1000001"

class MockConfig:
    async def get_config(self):
        return {
            "is_running": True, 
            "strategy_settings": {
                "time_range": {"start": "09:30", "end": "10:30", "check_condition": "09:16", "strategy_exit": "09:22"},
                "buffer_minutes": 5,
                "instrument": "NIFTY BANK"
            }
        }
    async def get_strategy_settings(self):
        return {
            "instrument": "NIFTY BANK",
            "strike_step": 100,
            "lots": 1,
            "lot_sizes": {"NIFTY BANK": 15},
            "paper_trading": True,
            "time_range": {"start": "09:30"},
            "legs": {
                "sp10ce": {"percentage_of_straddle": 10, "lots": 5, "expiry_type": "current", "action": "BUY", "sl_percentage": 20, "entry_trigger_percentage": 10, "reentry_trigger_percentage": 10},
                "sp10pe": {"percentage_of_straddle": 10, "lots": 1, "expiry_type": "current", "action": "BUY", "sl_percentage": 20, "entry_trigger_percentage": 10, "reentry_trigger_percentage": 10}
            }
        }

# Inject Mocks into sys.modules/classes
import db_client
import angel_client
import config_manager

db_client.DatabaseClient = MockDB
angel_client.AngelClient = MockAngel
config_manager.ConfigManager = MockConfig

# NOW import strategy engine
from strategy_engine import StrategyEngine

async def run_test():
    logger.info("--- Starting E2E Verification ---")
    
    engine = StrategyEngine()
    
    # 1. Initialize
    logger.info("[1] Initializing...")
    await engine.db.connect()
    
    # 2. Test Select Strikes
    logger.info("[2] Testing select_strikes()...")
    # Force state to IDLE
    engine.state["status"] = "IDLE"
    success = await engine.select_strikes()
    
    if success:
        logger.info("✅ select_strikes SUCCEEDED")
    else:
        logger.error("❌ select_strikes FAILED")
        return

    # Verify legs populated
    if "sp10ce" in engine.state["legs"] and engine.state["legs"]["sp10ce"]["status"] == "WAITING_RANGE":
        logger.info("✅ Legs populated correctly")
    else:
        logger.error(f"❌ Legs state incorrect: {engine.state['legs']}")

    # 3. Test Finalize Ranges
    logger.info("[3] Testing finalize_ranges()...")
    # Check if method exists (it crashed here before)
    if not hasattr(engine, 'finalize_ranges'):
         logger.error("❌ method finalize_ranges MISSING")
         return

    success_range = await engine.finalize_ranges()
    if success_range:
        logger.info("✅ finalize_ranges SUCCEEDED")
    else:
        logger.error("❌ finalize_ranges FAILED (Mock DB might return None?)")

    # Verify status transition
    sp10ce = engine.state["legs"]["sp10ce"]
    if sp10ce["status"] == "WAITING_ENTRY" and sp10ce["range_high"] == 250.0:
        logger.info("✅ Leg status transitioned to WAITING_ENTRY with Range High 250.0")
    else:
        logger.error(f"❌ Leg status mismatch: {sp10ce}")

    logger.info("--- Test Completed Successfully ---")

if __name__ == "__main__":
    asyncio.run(run_test())
