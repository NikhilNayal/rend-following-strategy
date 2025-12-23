import asyncio
from db_client import DatabaseClient
from dotenv import load_dotenv

load_dotenv()

async def check_options_sym():
    db = DatabaseClient()
    await db.connect()
    
    print("\n--- Checking Option Symbols for BANKNIFTY ---")
    query = "SELECT tradingsymbol FROM ticks_options WHERE tradingsymbol LIKE 'BANKNIFTY%' LIMIT 3"
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
        for r in rows:
            print(f"Found: {r['tradingsymbol']}")
        
        if not rows:
             print("No BANKNIFTY% symbols found. Checking 'NIFTY BANK%'...")
             rows2 = await conn.fetch("SELECT tradingsymbol FROM ticks_options WHERE tradingsymbol LIKE 'NIFTY BANK%' LIMIT 3")
             for r in rows2:
                 print(f"Found: {r['tradingsymbol']}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_options_sym())
