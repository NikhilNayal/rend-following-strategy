import asyncio
import os
import json
from db_client import DatabaseClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def verify():
    print("--- Verifying Data Freshness ---")
    
    # Load Config to see what to check
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            settings = config["strategy_settings"]
            instrument = settings["instrument"]
            mapping = settings["instrument_map"]
            db_symbol = mapping[instrument] 
    except Exception as e:
        print(f"Error reading config: {e}. Defaulting to NIFTY BANK")
        instrument = "NIFTY BANK"
        db_symbol = "BANKNIFTY"

    print(f"Target Instrument: {instrument} (DB Symbol: {db_symbol})")

    db = DatabaseClient()
    await db.connect()
    
    # Check Spot
    print(f"\nChecking Spot Data ({db_symbol})...")
    try:
        spot = await db.get_latest_spot_price(db_symbol)
        if spot:
            print(f"✅ Spot Data Found: {spot}")
        else:
            print(f"❌ Spot Data NOT Found or Stale for {db_symbol}")
    except Exception as e:
        print(f"Error checking spot: {e}")

    # Check Options
    print("\nChecking Options Data...")
    try:
        # Check specific instrument options if possible, or general
        query = "SELECT * FROM ticks_options WHERE tradingsymbol LIKE $1 ORDER BY time DESC LIMIT 1"
        search_pattern = f"{db_symbol}%"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, search_pattern)
            if row:
                print(f"✅ Latest Option Tick ({db_symbol}): {row['tradingsymbol']} at {row['time']} (Price: {row['last_price']})")
                
                # Check latency
                now = datetime.now()
                # Naive check if row matches
                if row['time'].tzinfo and not now.tzinfo:
                     now = now.astimezone(row['time'].tzinfo)
                
                diff = (now - row['time']).total_seconds()
                print(f"   Latency: {diff:.2f} seconds")
                
            else:
                print(f"❌ No Options Data Found for {db_symbol}")
    except Exception as e:
         print(f"Error checking options: {e}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(verify())
