# Configuration Guide - config.json

This document explains every field in `config.json` and its purpose.

## Top-Level Structure

### `strategy_settings`
Contains all strategy-related configuration parameters.

### `app_settings`
Contains application-level settings for credentials and connections.

### `is_running`
**Type:** `boolean`  
**Purpose:** Master switch to control strategy execution  
**Values:**
- `true` - Strategy is active and will execute trades
- `false` - Strategy is paused

---

## Strategy Settings

### `paper_trading`
**Type:** `boolean`  
**Purpose:** Enable/disable paper trading mode  
**Values:**
- `true` - Simulated trades (no real money)
- `false` - Live trading with real money  
**⚠️ WARNING:** Set to `false` only when ready for live trading!

---

### `time_range`
Controls the strategy's daily schedule.

#### `start`
**Type:** `string` (HH:MM format)  
**Purpose:** Time when strike selection happens and range monitoring begins  
**Example:** `"09:30"` - Strategy starts at 9:30 AM

#### `end`
**Type:** `string` (HH:MM format)  
**Purpose:** Time when range monitoring ends and active trading begins  
**Example:** `"10:30"` - Active trading starts at 10:30 AM

#### `check_condition`
**Type:** `string` (HH:MM format)  
**Purpose:** Time to check for gap-down conditions that may trigger emergency exits  
**Example:** `"09:16"` - Check for gaps at 9:16 AM

#### `strategy_exit`
**Type:** `string` (HH:MM format)  
**Purpose:** Time to square off all positions and reset for the next day  
**Example:** `"09:22"` - Exit all positions at 9:22 AM

---

### `instrument_map`
**Type:** `object`  
**Purpose:** Maps user-friendly instrument names to database symbols  
**Format:** `"User-Friendly Name": "Database Symbol"`

**Available Mappings:**
- `"NIFTY BANK"` → `"BANKNIFTY"`
- `"NIFTY 50"` → `"NIFTY"`
- `"SENSEX"` → `"SENSEX"`
- `"FINNIFTY"` → `"FINNIFTY"`
- `"MIDCPNIFTY"` → `"MIDCPNIFTY"`

---

### `strategy_parameters`
Advanced strategy timing and calculation parameters.

#### `gap_check_window_minutes`
**Type:** `integer`  
**Purpose:** Time window (in minutes) after `check_condition` to monitor for gap conditions  
**Example:** `2` - Monitor for 2 minutes after 9:16 AM

#### `exit_check_window_minutes`
**Type:** `integer`  
**Purpose:** Time window (in minutes) after `strategy_exit` to execute square-off  
**Example:** `3` - Execute exits within 3 minutes of exit time

#### `default_strike_step`
**Type:** `integer`  
**Purpose:** Default strike price interval for options  
**Example:** `100` - Strikes are 45000, 45100, 45200, etc.

#### `default_buffer_minutes`
**Type:** `integer`  
**Purpose:** Default buffer time (in minutes) after start time to allow strike selection  
**Example:** `30` - Allow 30 minutes for strike selection

---

### `expiry_type`
**Type:** `string`  
**Purpose:** Default expiry to use for all legs  
**Values:**
- `"current"` - Use nearest expiry
- `"next"` - Use following expiry

---

### `lots`
**Type:** `integer`  
**Purpose:** Global multiplier for all leg lots  
**Example:** `1` - Use configured lot sizes as-is  
**Example:** `2` - Double all position sizes

---

### `instrument`
**Type:** `string`  
**Purpose:** Primary instrument to trade  
**Value:** Must match a key in `instrument_map`  
**Example:** `"NIFTY BANK"`

---

### `strike_step`
**Type:** `integer`  
**Purpose:** Strike price interval for the selected instrument  
**Note:** Overrides `default_strike_step`  
**Example:** `100` for BANKNIFTY, `50` for NIFTY

---

### `buffer_minutes`
**Type:** `integer`  
**Purpose:** Buffer time in minutes after start time for strike selection  
**Note:** Overrides `default_buffer_minutes`  
**Example:** `30` - Allow 30 minutes after 9:30 AM for selection

---

### `lot_sizes`
**Type:** `object`  
**Purpose:** Defines lot size for each instrument  
**Format:** `"Instrument": lot_size`

**Standard Lot Sizes:**
- `"NIFTY BANK"`: `15` (1 lot = 15 shares)
- `"NIFTY 50"`: `25` (1 lot = 25 shares)
- `"SENSEX"`: `10` (1 lot = 10 shares)
- `"FINNIFTY"`: `25` (1 lot = 25 shares)
- `"MIDCPNIFTY"`: `50` (1 lot = 50 shares)

---

### `legs`
**Type:** `object`  
**Purpose:** Defines each trading leg (option position)

Each leg has the following structure:

#### Leg Name
**Format:** `sp{percentage}{ce|pe}`  
**Examples:**
- `sp10ce` - Straddle Premium 10% Call Option
- `sp5pe` - Straddle Premium 5% Put Option

#### `action`
**Type:** `string`  
**Purpose:** Action to take for this leg  
**Values:** `"BUY"` or `"SELL"`

#### `percentage_of_straddle`
**Type:** `integer`  
**Purpose:** Target premium as percentage of ATM straddle  
**Example:** `10` - Select option priced at 10% of straddle premium  
**Calculation:** If straddle = 500, target = 50

#### `sl_percentage`
**Type:** `integer`  
**Purpose:** Stop loss percentage from entry price  
**Example:** `50` - Exit if price drops 50% from entry  
**Calculation:** Entry at 100 → SL at 50

#### `entry_trigger_percentage`
**Type:** `integer`  
**Purpose:** Entry trigger above range high  
**Example:** `10` - Enter when price crosses `range_high + 10%`  
**Calculation:** Range high = 100 → Enter at 110

#### `reentry_trigger_percentage`
**Type:** `integer`  
**Purpose:** Re-entry trigger after stop loss  
**Example:** `10` - Re-enter when price crosses `range_high + 10%`  
**Note:** Maximum 2 entries allowed per leg

#### `lots`
**Type:** `integer`  
**Purpose:** Number of lots for this leg  
**Note:** Multiplied by global `lots` setting  
**Example:** `5` lots × global `1` = 5 total lots

#### `expiry_type`
**Type:** `string`  
**Purpose:** Expiry to use for this specific leg  
**Values:** `"current"` or `"next"`  
**Note:** Overrides global `expiry_type`

---

## App Settings

### `angel_one_credentials_env`
**Type:** `boolean`  
**Purpose:** Determines where to read Angel One API credentials  
**Values:**
- `true` - Read from `.env` file
- `false` - Read from this config file

### `db_connection_env`
**Type:** `boolean`  
**Purpose:** Determines where to read database connection details  
**Values:**
- `true` - Read from `.env` file
- `false` - Read from this config file

---

## Example Configuration Scenarios

### Conservative Day Trading
```json
{
  "time_range": {
    "start": "09:30",
    "end": "10:30"
  },
  "lots": 1,
  "sl_percentage": 30
}
```

### Aggressive Intraday
```json
{
  "time_range": {
    "start": "09:15",
    "end": "15:15"
  },
  "lots": 3,
  "sl_percentage": 50
}
```

### Testing/Paper Trading
```json
{
  "paper_trading": true,
  "is_running": false,
  "lots": 1
}
```
