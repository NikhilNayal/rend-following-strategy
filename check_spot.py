import asyncio
import os
from db_client import DatabaseClient
from dotenv import load_dotenv

load_dotenv()

async def check_spot_symbols():
    db = DatabaseClient()
    await db.connect()
    
    print("\n--- Available Spot Symbols ---")
    try:
        query = "SELECT DISTINCT tradingsymbol FROM ticks_spot"
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query)
            for r in rows:
                print(f"Found: {r['tradingsymbol']}")
            
            if not rows:
                print("No rows in ticks_spot")
                
    except Exception as e:
        print(f"Error: {e}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_spot_symbols())
