
import asyncio
import json
import os
from datetime import datetime, time, timedelta
import logging
from typing import Dict, Optional

# Assuming these are in the same package
from db_client import DatabaseClient
from angel_client import AngelClient
from config_manager import ConfigManager

# Setup Logging
# This allows the robot to talk to us via the terminal or files.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("StrategyEngine")

class StrategyEngine:
    """
    This is the BRAIN of the operation. 
    It makes all the decisions: when to buy, when to sell, and what to watch.
    """
    def __init__(self):
        self.db = DatabaseClient()        # The eyes (reading data)
        self.angel = AngelClient()        # The hands (placing orders)
        self.config_manager = ConfigManager() # The instruction manual
        self.state_file = "strategy_state.json" # The memory (notebook)
        
        # Runtime State
        # This is where the brain keeps track of what it's doing right now.
        self.state = {
            "status": "IDLE", # Could be: IDLE (sleeping), MONITORING_RANGE (watching), ACTIVE (trading)
            "legs": {},       # Details about the specific options we are trading (e.g. 45000 CE)
            "current_phase": None,
            "selected_expiry": None,
            "exit_triggered": False,
            "instrument": None 
        }

    async def load_state(self):
        """
        Wake up and read the notebook (file) to remember what happened before.
        """
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
                logger.info("State loaded from file.")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    async def save_state(self):
        """
        Write everything down in the notebook so we don't forget if the power goes out.
        """
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def start(self):
        """
        THE MAIN LOOP.
        This is the heartbeat of the robot. It runs forever, checking the clock and making decisions.
        """
        logger.info("Strategy Engine Started")
        await self.db.connect()     # Open connection to the database
        await self.load_state()     # Restore memory
        
        # 1. Login to Broker (unless we are just pretending/paper trading)
        config = await self.config_manager.get_strategy_settings()
        if not config["paper_trading"]:
            self.angel.login()
        else:
            logger.info("Paper Trading Mode: Skipping Angel One Login.")

        # 2. Setup empty slots for the Option Legs so the Dashboard has something to show
        if not self.state["legs"]:
             config = await self.config_manager.get_strategy_settings()
             legs_config = config["legs"]
             for leg_key, details in legs_config.items():
                 self.state["legs"][leg_key] = {
                     "strike": 0, "token": 0, "symbol": "Waiting...",
                     "status": "IDLE", "lots": details["lots"],
                     "range_high": 0, "range_low": 0,
                     "entry_price": 0, "sl_price": 0
                 }

        last_log_time = datetime.min
        
        # 3. Start the infinite loop!
        while True:
            try:
                # Refresh our instructions (Config) every loop
                config = await self.config_manager.get_config()
                
                # --- HEARTBEAT --- 
                # Every 60 seconds, say "I am alive!" in the logs.
                if (datetime.now() - last_log_time).total_seconds() > 60:
                    is_running = config['is_running'] if config else False
                    logger.info(f"Strategy Heartbeat | Status: {self.state['status']} | Config Running: {is_running}")
                    last_log_time = datetime.now()

                # If the "ON/OFF" switch is OFF, sleep for 5 seconds and check again.
                if not config["is_running"]:
                    await asyncio.sleep(5)
                    continue

                # Get the current time on the clock
                now = datetime.now()
                current_time = now.time()

                # Read the time instructions from the config
                settings = config["strategy_settings"]
                time_range = settings["time_range"]
                
                # Convert strings "09:30" into Time objects the computer understands
                start_str = time_range["start"]
                end_str = time_range["end"]
                check_cond_str = time_range["check_condition"]
                exit_str = time_range["strategy_exit"]
                
                start_h, start_m = map(int, start_str.split(':'))
                end_h, end_m = map(int, end_str.split(':'))
                check_h, check_m = map(int, check_cond_str.split(':'))
                exit_h, exit_m = map(int, exit_str.split(':'))
                
                start_time = time(start_h, start_m)
                end_time = time(end_h, end_m)
                check_time = time(check_h, check_m)
                exit_time = time(exit_h, exit_m)
                
                # --- DECISION TIME: What should I do right now? ---

                strategy_params = settings["strategy_parameters"]
                gap_window = strategy_params["gap_check_window_minutes"]
                
                # TASK 1: Morning Panic Check (9:16 AM)
                # Did the market open with a huge gap that hit our Stop Loss?
                if current_time >= check_time and current_time < time(check_h, check_m + gap_window):
                    await self.check_gap_condition()

                # TASK 2: Daily Cleanup (9:22 AM or configured Exit Time)
                # Determine "Game Over" for the day. Close everything and reset for tomorrow.
                exit_window = strategy_params["exit_check_window_minutes"]
                if current_time >= exit_time and current_time < time(exit_h, exit_m + exit_window):
                    if self.state["status"] != "IDLE":
                        logger.info(f"Triggering Daily Strategy Exit at {exit_str}")
                        await self.execute_strategy_exit()
                        
                        logger.info("Resetting strategy for new trading day...")
                        self.state["status"] = "IDLE"
                        self.state["legs"] = {}
                        self.state["exit_triggered"] = False
                        self.state["selected_expiry"] = None
                        await self.save_state()

                # TASK 3: Start Conditions (e.g. 10:20 AM)
                # Is it time to start? We have a small "Buffer" window to catch this moment.
                default_buffer = strategy_params["default_buffer_minutes"]
                buffer_mins = settings["buffer_minutes"]
                start_buffer = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=buffer_mins)).time()
                
                if current_time >= start_time and current_time < start_buffer and self.state["status"] == "IDLE":
                    logger.info(f"Triggering Start at {start_str}")
                    # STEP 1: Pick the Striker (Options) to play with today.
                    success = await self.select_strikes()
                    if success:
                        self.state["status"] = "MONITORING_RANGE"
                        await self.save_state()
                    else:
                        logger.error("Strike selection failed. Retrying in next loop...")


                # TASK 4: Watch The Market (Usually 9:30 to 10:30)
                # We are just watching the High and Low prices. We do nothing else.
                if self.state["status"] == "MONITORING_RANGE":
                    if current_time >= end_time:
                         logger.info(f"Range Monitoring Ended at {end_str}. Activating Strategy.")
                         # STEP 2: Lock in the High/Low prices as our triggers.
                         await self.finalize_ranges()
                         self.state["status"] = "ACTIVE"
                         await self.save_state()

                # TASK 5: ACTIVE TRADING
                # The waiting is over. If price crosses our lines, we BUY/SELL!
                if self.state["status"] == "ACTIVE":
                   await self.monitor_and_execute()
                   
                # Sleep for 2 seconds so we don't melt the CPU by running too fast.
                await asyncio.sleep(1) 
                await asyncio.sleep(1) 

            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                await asyncio.sleep(5)


    # Instrument Name Mapping is now loaded from config.json


    async def get_expiry(self, instrument: str, type_pref: str):
        """
        Helper: Find out what 'Current Expiry' means today.
        e.g. If today is Monday, Current might be this Thursday.
        """
        # type_pref: "current" or "next"
        # Ensure we use the mapped symbol for DB queries
        config = await self.config_manager.get_strategy_settings()
        mapping = config["instrument_map"]
        db_instrument = mapping[instrument]
        expiries = await self.db.get_active_expiries(db_instrument)
        if not expiries:
            return None
            
        if type_pref == "next" and len(expiries) > 1:
            return expiries[1]
        return expiries[0]

    async def select_strikes(self):
        """
        Crucial Step: Selecting the players for the game.
        We look at the market price at the START TIME (e.g. 10:20) and pick options based on that.
        """
        logger.info("Selecting Strikes...")
        config = await self.config_manager.get_strategy_settings()
        instrument = config["instrument"]
        
        # 1. Figure out WHEN we were supposed to start (e.g. 10:20 AM)
        time_range = config["time_range"]
        start_str = time_range["start"]
        start_h, start_m = map(int, start_str.split(':'))
        now = datetime.now()
        selection_time = datetime.combine(now.date(), time(start_h, start_m))
        
        # Safety: If we are running BEFORE the start time (testing?), use Now.
        if now < selection_time:
             logger.warning(f"Strategy triggered before start time {start_str}? Using current time.")
             selection_time = now

        logger.info(f"Using Selection Time: {selection_time}")

        # Store instrument & time
        self.state["instrument"] = instrument
        
        # Get the right symbol for the database (NIFTY BANK -> BANKNIFTY)
        mapping = config["instrument_map"]
        db_instrument = mapping[instrument]
        
        # 2. Get the Spot Price at that EXACT time.
        spot_price = await self.db.get_spot_price_at(instrument, selection_time)
        if not spot_price:
            logger.error(f"Could not fetch spot price for {instrument} at {selection_time}")
            return False

        # 3. Calculate At-The-Money (ATM) Strike
        # e.g. Spot 45030 -> Round to nearest 100 -> 45000 is ATM
        strategy_params = config["strategy_parameters"]
        default_step = strategy_params["default_strike_step"]
        step = config["strike_step"]
        atm_strike = round(spot_price / step) * step
        
        # 4. Get Expiry Date
        current_expiry = await self.get_expiry(db_instrument, "current")
        if not current_expiry:
            logger.error(f"No active current expiry found for {db_instrument}")
            return False

        # 5. Look up the ATM Call options and Put options to check their price.
        ce_token = await self.db.get_token_for_strike(db_instrument, atm_strike, "CE", current_expiry)
        pe_token = await self.db.get_token_for_strike(db_instrument, atm_strike, "PE", current_expiry)
        
        # Get their price AT THE SELECTION TIME
        ce_data = await self.db.get_option_price_at(ce_token, selection_time) if ce_token else None
        pe_data = await self.db.get_option_price_at(pe_token, selection_time) if pe_token else None
        
        if not ce_data or not pe_data:
             logger.error(f"Could not fetch ATM premiums at {selection_time}")
             return False

        # 6. Calculate Straddle Premium (CE Price + PE Price)
        # This tells us how "expensive" the market is right now.
        straddle_premium = ce_data + pe_data
        logger.info(f"Spot: {spot_price}, ATM: {atm_strike}, Straddle Prem: {straddle_premium:.2f} (at {selection_time.time()})")

        # Inner helper to find the best option
        async def find_leg(target_pct, opt_type, type_pref="current"):
            leg_expiry = await self.get_expiry(db_instrument, type_pref)
            if not leg_expiry:
                return None, 0
            
            # Target Price = Percentage of Straddle Premium
            # e.g. If Straddle is 500 and we want 10%, we look for options priced around 50.
            target_premium = straddle_premium * (target_pct / 100.0)
            
            # Ask DB for all strikes at that historical time
            candidates = await self.db.get_available_strikes_at(db_instrument, leg_expiry, opt_type, selection_time)
            
            # Find the one closest to our Target Price
            best = min(candidates, key=lambda x: abs(x['last_price'] - target_premium)) if candidates else None
            return best, target_premium

        legs = config["legs"]
        for leg_key, details in legs.items():
            opt_type = "CE" if "ce" in leg_key else "PE"
            pct = details["percentage_of_straddle"]
            expiry_pref = details["expiry_type"]
            action = details["action"]
            
            best_strike, target_prem = await find_leg(pct, opt_type, expiry_pref)
            
            if best_strike:
                # Save the selected strike to our notebook (state)
                self.state["legs"][leg_key] = {
                    "strike": best_strike['strike_price'],
                    "token": best_strike['token'],
                    "symbol": best_strike['symbol'],
                    "expiry": best_strike.get('expiry', expiry_pref),
                    "action": action, 
                    "ref_premium": target_prem,
                    "status": "WAITING_RANGE",
                    "range_high": 0,
                    "range_low": 0,
                    "entry_price": 0,
                    "sl_price": 0,
                    "lots": details["lots"],
                    "sl_pct": details["sl_percentage"],
                    "entry_trigger_pct": details["entry_trigger_percentage"],
                    "reentry_trigger_pct": details["reentry_trigger_percentage"],
                    "entries_count": 0
                }
                logger.info(f"Selected {leg_key}: Strike {best_strike['strike_price']} at {best_strike['last_price']} ({action})")
        
        return True

    async def finalize_ranges(self):
        """
        Step 2: Lock in the High and Low prices.
        We look back at the DB between 'Start Time' and 'Now' to see the High/Low.
        """
        logger.info("Finalizing Ranges...")
        
        config = await self.config_manager.get_strategy_settings()
        start_str = config["time_range"]["start"]
        start_h, start_m = map(int, start_str.split(':'))
        
        now = datetime.now()
        start_dt = datetime.combine(now.date(), time(start_h, start_m))
        
        success_count = 0
        for leg_key, leg_data in self.state["legs"].items():
            if leg_data.get("status") == "DONE":
                 continue
                 
            token = leg_data["token"]
            # ASK DB: "What was the High and Low for this token since start time?"
            high_low = await self.db.get_range_high_low(token, start_dt, now)
            
            if high_low.get("high") is not None:
                leg_data["range_high"] = float(high_low["high"])
                leg_data["range_low"] = float(high_low["low"])
                leg_data["status"] = "WAITING_ENTRY" # Now we wait for entry trigger!
                success_count += 1
                logger.info(f"{leg_key} Range: Low {leg_data['range_low']} - High {leg_data['range_high']}")
            else:
                logger.warning(f"No range data found for {leg_key} (Token: {token})")
                
        if success_count > 0:
            logger.info(f"Ranges finalized for {success_count} legs.")
            return True
        else:
            logger.warning("No ranges could be finalized.")
            return False

    async def select_strikes_at_time(self, timestamp: datetime) -> bool:
        # Placeholder for historical testing if needed
        pass 

    async def monitor_and_execute(self):
        """
        Active Trading Monitor.
        Checks every leg to see if we should ENTRY or EXIT.
        """
        tasks = []
        for leg_key, leg_data in self.state["legs"].items():
            tasks.append(self.check_leg_logic(leg_key, leg_data))
        
        # Run all checks at simpler parallel
        await asyncio.gather(*tasks)

    async def check_leg_logic(self, leg_key, leg_data):
        try:
            # 1. Get the LIVE price right now
            current_price = await self.db.get_option_price(leg_data["token"])
            if not current_price:
                return

            status = leg_data["status"]
            range_high = leg_data["range_high"]
            action = leg_data["action"]
            
            # CASE A: WAITING FOR FIRST ENTRY
            if status == "WAITING_ENTRY":
                # Entry Rule: Price > Range High + X%
                trigger_pct = leg_data["entry_trigger_pct"] 
                trigger_price = range_high * (1 + trigger_pct / 100.0)
                
                if current_price > trigger_price:
                    await self.execute_entry(leg_key, leg_data, current_price, "ENTRY_1")

            # CASE B: POSITION IS OPEN ("ACTIVE")
            elif status == "ACTIVE":
                # Check Stop Loss (Safety Net)
                sl_hit = False
                if action == "BUY":
                    if current_price <= leg_data["sl_price"]: sl_hit = True
                else: # SELL
                    if current_price >= leg_data["sl_price"]: sl_hit = True

                if sl_hit:
                    await self.execute_exit(leg_key, leg_data, current_price, "SL_HIT")
                    
                    # If we haven't entered twice already, get ready to RE-ENTER.
                    if leg_data["entries_count"] < 2:
                        leg_data["status"] = "WAITING_REENTRY"
                    else:
                        leg_data["status"] = "DONE" # Max entries reached. Done for the day.

            # CASE C: WAITING FOR RE-ENTRY
            elif status == "WAITING_REENTRY":
                 # Re-Entry uses SECOND trigger pct (config)
                 trigger_pct = leg_data["reentry_trigger_pct"]
                 trigger_price = range_high * (1 + trigger_pct / 100.0)
                 
                 if current_price > trigger_price:
                      await self.execute_entry(leg_key, leg_data, current_price, "ENTRY_2")
        
        except Exception as e:
            logger.error(f"Error checking logic for {leg_key}: {e}")

    async def execute_entry(self, leg_key, leg_data, price, description):
        logger.info(f"Executing {description} for {leg_key} at {price}")
        
        config = await self.config_manager.get_strategy_settings()
        
        # Calculate how many lots to buy
        instrument = self.state.get("instrument", config["instrument"])
        lot_sizes = config["lot_sizes"]
        lot_size = lot_sizes[instrument]
        
        global_multiplier = config["lots"]
        qty = leg_data["lots"] * global_multiplier * lot_size
        
        action = leg_data["action"]
        
        if config["paper_trading"]:
             # Just pretend to trade!
             logger.info(f"[PAPER TRADE] {action} {leg_data['symbol']} Qty: {qty} @ {price}")
             order_id = "PAPER_" + datetime.now().strftime("%H%M%S")
        else:
             try:
                 # Real Trade! Call the Broker.
                 # We wrap this in a timeout so if broker is slow, we don't freeze.
                 loop = asyncio.get_event_loop()
                 order_id = await asyncio.wait_for(
                     loop.run_in_executor(
                         None, 
                         lambda: self.angel.place_order(
                             leg_data["symbol"], 
                             leg_data["token"],
                             action, 
                             qty
                         )
                     ),
                     timeout=2.0
                 )
             except asyncio.TimeoutError:
                 logger.error(f"Order Placement TIMEOUT for {leg_key}")
                 order_id = None
             except Exception as e:
                 logger.error(f"Order Placement Failed for {leg_key}: {e}")
                 order_id = None
        
        if order_id:
            leg_data["status"] = "ACTIVE"
            leg_data["entry_price"] = price
            
            # Calculate Stop Loss immediately upon entry
            sl_pct = leg_data["sl_pct"]
            if action == "BUY":
                leg_data["sl_price"] = price * (1 - sl_pct / 100.0)
            else: # SELL
                leg_data["sl_price"] = price * (1 + sl_pct / 100.0)
                
            leg_data["entries_count"] += 1
            logger.info(
                f"{leg_key} entry successful ({action}). Order ID: {order_id}, "
                f"Entry: {price}, SL: {leg_data['sl_price']:.2f}"
            )
            await self.save_state()
        else:
            logger.error(f"Failed to execute entry for {leg_key}")

    async def execute_exit(self, leg_key, leg_data, price, reason):
        logger.info(f"Exiting {leg_key} at {price} due to {reason}")
        
        config = await self.config_manager.get_strategy_settings()
        instrument = self.state.get("instrument", config["instrument"])
        lot_sizes = config["lot_sizes"]
        lot_size = lot_sizes[instrument]
        
        global_multiplier = config["lots"]
        qty = leg_data["lots"] * global_multiplier * lot_size
        
        # To EXIT a position, we do the opposite. If we BOUGHT, now we SELL.
        entry_action = leg_data["action"]
        exit_action = "SELL" if entry_action == "BUY" else "BUY"
        
        if config["paper_trading"]:
            logger.info(f"[PAPER TRADE] {exit_action} {leg_data['symbol']} Qty: {qty} @ {price} ({reason})")
        else:
            try:
                loop = asyncio.get_event_loop()
                order_id = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, 
                        lambda: self.angel.place_order(
                            leg_data["symbol"],
                            leg_data["token"],
                            exit_action,
                            qty
                        )
                    ),
                    timeout=2.0
                )
                if order_id:
                    logger.info(f"Exit order placed for {leg_key}. Order ID: {order_id}")
            except asyncio.TimeoutError:
                 logger.error(f"Exit Order Placement TIMEOUT for {leg_key}")
            except Exception as e:
                logger.error(f"Exit order failed for {leg_key}: {e}")
            
        leg_data["status"] = "EXITED" 
        leg_data["exit_price"] = price
        leg_data["exit_reason"] = reason
        await self.save_state()

    async def check_exit_condition(self):
        # Placeholder for other checks
        pass

    async def check_gap_condition(self):
        """
        Runs at 9:16 AM. 
        Safety Check: Did the market open WAY below where we wanted? If so, run away!
        """
        logger.info("Running 9:16 AM Gap Panic Check...")
        tasks = []
        for leg_key, leg_data in self.state["legs"].items():
            if leg_data["status"] == "ACTIVE":
                current_price = await self.db.get_option_price(leg_data["token"])
                if not current_price:
                    continue
                
                # Check for gap below SL
                if current_price <= leg_data["sl_price"]:
                    logger.warning(f"GAP DOWN DETECTED on {leg_key}! Price {current_price} < SL {leg_data['sl_price']}")
                    tasks.append(self.execute_exit(leg_key, leg_data, current_price, "GAP_SL_HIT"))
        
        if tasks:
            await asyncio.gather(*tasks)

    async def execute_strategy_exit(self):
        """
        Runs at the end of the day (e.g. 9:22 AM in config or 3:30 PM).
        Forces everything to close so we are flat for the next day.
        """
        logger.info("Executing Strategy Square Off...")
        tasks = []
        for leg_key, leg_data in self.state["legs"].items():
             if leg_data["status"] == "ACTIVE":
                 tasks.append(self.execute_exit(leg_key, leg_data, 0, "DAILY_SQUARE_OFF"))
             
             elif leg_data["status"] in ["WAITING_ENTRY", "WAITING_REENTRY"]:
                 leg_data["status"] = "DONE"
        
        if tasks:
            await asyncio.gather(*tasks)


