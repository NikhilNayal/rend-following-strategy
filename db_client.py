
import asyncpg
import os
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from utils import parse_tradingsymbol, parse_expiry_sort_key

# We set up a "log" so we can write down any errors or important events in a file/console.
logger = logging.getLogger("DatabaseClient")

class DatabaseClient:
    """
    This class is like a Librarian. Its job is to talk to the "Database" (Library)
    where all the market data is stored.
    """
    def __init__(self):
        # These are like the keys and address to the Library.
        self.user = os.getenv("POSTGRES_USER")
        self.password = os.getenv("POSTGRES_PASSWORD")
        self.db = os.getenv("POSTGRES_DB")
        self.host = os.getenv("POSTGRES_HOST")
        self.port = os.getenv("POSTGRES_PORT")
        self.pool = None # This will hold our connection to the library.

    async def connect(self):
        """
        Open the door to the Library so we can start asking questions.
        """
        if not self.pool:
            try:
                # We create a "pool" of connections. Think of it as having 
                # multiple phone lines open to the library so we can ask many questions at once.
                self.pool = await asyncpg.create_pool(
                    user=self.user,
                    password=self.password,
                    database=self.db,
                    host=self.host,
                    port=self.port
                )
                print("Connected to Database")
            except Exception as e:
                print(f"Database connection failed: {e}")
                raise

    async def disconnect(self):
        """
        Hang up the phone and close the door to the Library.
        """
        if self.pool:
            await self.pool.close()
            print("Disconnected from Database")

    async def get_latest_spot_price(self, instrument: str) -> Optional[float]:
        """
        Question: "What is the CURRENT price of NIFTY BANK?"
        
        We look at the 'ticks_spot' table.
        We only look at data from the last 10 minutes (Optimization).
        Why? Because searching the whole year's history would be too slow! 
        we only care about what is happening RIGHT NOW.
        """
        query = """
            SELECT last_price, time, NOW() as db_now
            FROM ticks_spot 
            WHERE tradingsymbol = $1 
            AND time > NOW() - INTERVAL '10 minutes'
            ORDER BY time DESC 
            LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, instrument)
                if row:
                    # Check if the data is "Fresh".
                    # If the milk in the fridge is 10 days old, you don't drink it.
                    # Similarly, if the price is 10 minutes old, it's too risky to trade on!
                    age = (row['db_now'] - row['time']).total_seconds()
                    if age > 600: # 600 seconds = 10 minutes
                        logger.warning(
                            f"Stale spot data for {instrument}: {age:.1f}s old. "
                            f"Check if data streaming is running."
                        )
                        return None
                    return float(row['last_price'])
                else:
                    logger.error(
                        f"No spot data found for {instrument} in last 10 mins. "
                        f"Verify instrument name and data streaming."
                    )
                    return None
        except Exception as e:
            logger.error(f"Error fetching spot price for {instrument}: {e}")
            return None

    async def get_active_expiries(self, instrument: str) -> List[str]:
        """
        Question: "What are the expiry dates available for NIFTY BANK?"
        (e.g., 26JAN, 26FEB)
        
        We scan the options table for the last day to see which dates are appearing.
        """
        query = """
            SELECT DISTINCT ON (tradingsymbol) tradingsymbol 
            FROM ticks_options 
            WHERE tradingsymbol LIKE $1 || '%'
            AND time > NOW() - INTERVAL '1 day'
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, instrument)
        
        parsed_expiries = set()
        for r in rows:
            # We use a tool to read the symbol "NIFTY25JAN..." and pull out "25JAN"
            parsed = parse_tradingsymbol(r['tradingsymbol'])
            if parsed and parsed['name'] == instrument:
                parsed_expiries.add(parsed['expiry_str'])
        
        # Sort them nicely so 26JAN comes before 26FEB
        return sorted(list(parsed_expiries), key=parse_expiry_sort_key)

    async def get_available_strikes(self, instrument: str, expiry_str: str, option_type: str) -> List[Dict]:
        """
        Question: "List all the Strike Prices (e.g. 45000, 45100) for a specific Expiry?"
        
        We look at the last 20 minutes of data to find all active strikes.
        """
        like_pattern = f"{instrument}{expiry_str}%{option_type}"
        
        query = """
            SELECT DISTINCT ON (tradingsymbol) 
                tradingsymbol, instrument_token, last_price 
            FROM ticks_options 
            WHERE tradingsymbol LIKE $1
            AND time > NOW() - INTERVAL '20 minutes'
            ORDER BY tradingsymbol, time DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, like_pattern)
        
        results = []
        for r in rows:
            parsed = parse_tradingsymbol(r['tradingsymbol'])
            if parsed and parsed['expiry_str'] == expiry_str and parsed['type'] == option_type:
                results.append({
                    "strike_price": parsed['strike'],
                    "last_price": r['last_price'],
                    "token": r['instrument_token'],
                    "symbol": r['tradingsymbol']
                })
        return results

    async def get_token_for_strike(self, instrument: str, strike: float, option_type: str, expiry_str: str) -> Optional[int]:
        """
        Question: "What is the unique ID (Token) for NIFTY 45000 CE?"
        Every option has a unique ID number used for faster lookup.
        """
        # Convert strike number to string (e.g. 45000.0 -> "45000")
        if isinstance(strike, int):
            strike_str = str(strike)
        elif isinstance(strike, float) and strike.is_integer():
            strike_str = str(int(strike))
        else:
            strike_str = str(strike)
        target_symbol = f"{instrument}{expiry_str}{strike_str}{option_type}"
        
        query = """
            SELECT instrument_token 
            FROM ticks_options 
            WHERE tradingsymbol = $1
            AND time > NOW() - INTERVAL '1 day'
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            token = await conn.fetchval(query, target_symbol)
            return token

    async def get_option_price(self, token: int) -> Optional[float]:
        """
        Question: "What is the CURRENT price for this specific Option ID?"
        
        Optimized: We only look back 20 minutes to avoid scanning millions of old rows.
        """
        query = """
            SELECT last_price, time
            FROM ticks_options 
            WHERE instrument_token = $1 
            AND time > NOW() - INTERVAL '20 minutes'
            ORDER BY time DESC 
            LIMIT 1
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, token)
                if row:
                    # FRESHNESS CHECK
                    # We compare the data timestamp with "Now".
                    # If it's too old (> 1200 seconds / 20 mins), we ignore it.
                    row_time = row['time']
                    now = datetime.now()
                    
                    # Timezone handling magic to make sure we compare Apples to Apples
                    if row_time.tzinfo is not None and now.tzinfo is None:
                         now = now.astimezone(row_time.tzinfo)
                    
                    age = (now - row_time).total_seconds()
                    
                    if age > 1200:
                        logger.warning(
                            f"Stale option data for token {token}: {age:.1f}s old. "
                            f"Check if data streaming is running."
                        )
                        return None
                    return float(row['last_price'])
                return None
        except Exception as e:
            logger.error(f"Error fetching option price for token {token}: {e}")
            return None

    async def get_range_high_low(self, token: int, start_time: datetime, end_time: datetime) -> Dict[str, float]:
        """
        Question: "What was the Higest and Lowest price between 9:30 AM and 10:30 AM?"
        
        This is used to figure out the "Range" of the market.
        """
        query = """
            SELECT MAX(last_price) as high, MIN(last_price) as low
            FROM ticks_options
            WHERE instrument_token = $1
            AND time >= $2
            AND time <= $3
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, token, start_time, end_time)
            return dict(row) if row else {"high": None, "low": None}

    # --- Time-Travel Methods (Back to the Future!) ---

    async def get_spot_price_at(self, instrument: str, timestamp: datetime) -> Optional[float]:
        """
        Time Travel: "What WAS the price of NIFTY BANK at exactly 10:20 AM?"
        
        We look for the newest tick that happened BEFORE or AT 10:20 AM.
        """
        query = """
            SELECT last_price 
            FROM ticks_spot 
            WHERE tradingsymbol = $1 
            AND time <= $2
            ORDER BY time DESC 
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(query, instrument, timestamp)
            return float(val) if val else None

    async def get_option_price_at(self, token: int, timestamp: datetime) -> Optional[float]:
        """
        Time Travel: "What WAS the price of this Option at 10:20 AM?"
        """
        query = """
            SELECT last_price 
            FROM ticks_options 
            WHERE instrument_token = $1 
            AND time <= $2
            ORDER BY time DESC 
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(query, token, timestamp)
            return float(val) if val else None

    async def get_available_strikes_at(self, instrument: str, expiry_str: str, option_type: str, timestamp: datetime) -> List[Dict]:
        """
        Time Travel: "List all strikes that were valid at 10:20 AM."
        
        We look back 15 minutes FROM 10:20 AM (so 10:05 to 10:20).
        """
        like_pattern = f"{instrument}{expiry_str}%{option_type}"
        
        # Look back 15 mins from the REQUESTED timestamp
        lookback = timestamp - timedelta(minutes=15)
        
        query = """
            SELECT DISTINCT ON (tradingsymbol) 
                tradingsymbol, instrument_token, last_price 
            FROM ticks_options 
            WHERE tradingsymbol LIKE $1
            AND time <= $2 
            AND time > $3
            ORDER BY tradingsymbol, time DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, like_pattern, timestamp, lookback)
            
        results = []
        for r in rows:
            parsed = parse_tradingsymbol(r['tradingsymbol'])
            if parsed and parsed['expiry_str'] == expiry_str and parsed['type'] == option_type:
                results.append({
                    "strike_price": parsed['strike'],
                    "last_price": r['last_price'],
                    "token": r['instrument_token'],
                    "symbol": r['tradingsymbol']
                })
        return results



