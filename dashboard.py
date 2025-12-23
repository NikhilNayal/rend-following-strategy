#!/usr/bin/env python3
import time
import requests
import sys
from datetime import datetime
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich import box
from rich.text import Text
from rich.align import Align

# Config
API_URL = "http://localhost:8000"
REFRESH_RATE = 1  # Seconds

console = Console()

def fetch_data():
    """Fetch all necessary data from the API"""
    try:
        # Get Status (Strategy State + Config)
        status_res = requests.get(f"{API_URL}/status", timeout=0.5)
        status_data = status_res.json()
        
        # Get Spot Price
        instrument = status_data['config']['strategy_settings']['instrument']
        spot_res = requests.get(f"{API_URL}/spot_price?instrument={instrument}", timeout=0.5)
        spot_data = spot_res.json()
        
        return {
            'status': status_data,
            'spot': spot_data
        }
    except Exception as e:
        return None

def make_header(data):
    """Create the header panel"""
    if not data:
        return Panel(Text("🔴 CONNECTION LOST - Trying to reconnect...", style="bold white on red"), style="red")
    
    state = data['status']['strategy_state']
    config = data['status']['config']
    spot = data['spot']
    
    # Status Style
    status_text = state['status']
    status_style = "bold green" if status_text == "ACTIVE" else "bold yellow"
    if status_text == "IDLE": status_style = "bold white"
    
    # Paper Trading Badge
    mode = "PAPER TRADING" if config['strategy_settings']['paper_trading'] else "LIVE TRADING"
    mode_style = "bold black on yellow" if "PAPER" in mode else "bold white on red"
    
    # Spot Price
    spot_price = spot.get('spot_price')
    spot_str = f"₹{spot_price:,.2f}" if spot_price else "Waiting..."
    instrument = spot.get('instrument', 'UNKNOWN')
    
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="right", ratio=1)
    
    grid.add_row(
        Text(f"🚀 TREND FOLLOWING STRATEGY", style="bold cyan"),
        Text(mode, style=mode_style),
        Text(f"{instrument}: {spot_str}", style="bold green" if spot_price else "dim")
    )
    
    return Panel(grid, style="blue", box=box.ROUNDED)

def make_legs_table(data):
    """Create the legs table"""
    table = Table(expand=True, box=box.MINIMAL_HEAVY_HEAD, border_style="bright_black")
    
    table.add_column("Leg", style="cyan")
    table.add_column("Strike", justify="right")
    table.add_column("Type", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Range High", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("SL", justify="right")
    table.add_column("LTP", justify="right", style="bold")
    
    if not data:
        return Panel(Align.center("Waiting for data..."), title="Active Legs")

    legs = data['status']['strategy_state'].get('legs', {})
    
    if not legs:
        # Get start time from config dynamically
        start_time = data['status']['config']['strategy_settings']['time_range']['start']
        return Panel(Align.center(f"No legs active (Waiting for {start_time} selection)"), title="Active Legs", border_style="blue")
        
    for leg_key, leg in legs.items():
        # Determine Color
        status = leg['status']
        style = "white"
        if status == "ACTIVE": style = "green"
        if status == "EXITED": style = "dim"
        
        # Format values
        strike = str(leg.get('strike', '-'))
        leg_type = "CE" if "ce" in leg_key else "PE"
        type_style = "green" if leg_type == "CE" else "red"
        
        range_high = f"{leg.get('range_high', 0):.2f}" if leg.get('range_high') else "-"
        entry = f"{leg.get('entry_price', 0):.2f}" if leg.get('entry_price') else "-"
        sl = f"{leg.get('sl_price', 0):.2f}" if leg.get('sl_price') else "-"
        
        # Placeholder for LTP since we don't have it in state yet
        ltp = "-" 
        
        table.add_row(
            leg_key.upper(),
            strike,
            Text(leg_type, style=type_style),
            Text(status, style=style),
            range_high,
            entry,
            sl,
            ltp
        )
        
    return Panel(table, title="Legs execution", border_style="blue")

def make_info_panel(data):
    """Create info panel with config and state details"""
    if not data: return Panel("")
    
    state = data['status']['strategy_state']
    config = data['status']['config']['strategy_settings']
    
    info = Table.grid(padding=(0, 2))
    info.add_column(style="dim")
    info.add_column(style="bold")
    
    info.add_row("Phase:", state.get('status', 'UNKNOWN'))
    info.add_row("Expiry:", state.get('selected_expiry', '-'))
    info.add_row("Start Time:", config['time_range']['start'])
    info.add_row("End Time:", config['time_range']['end'])
    info.add_row("Lots:", str(config['lots']))
    
    return Panel(info, title="Strategy Info", border_style="green")

def make_layout():
    """Define the UI layout"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1)
    )
    layout["body"].split_row(
        Layout(name="main", ratio=3),
        Layout(name="sidebar", ratio=1)
    )
    return layout

def update_layout(layout, data):
    """Update layout with new data"""
    layout["header"].update(make_header(data))
    layout["main"].update(make_legs_table(data))
    layout["sidebar"].update(make_info_panel(data))

def main():
    console.clear()
    console.print("🚀 Starting Dashboard...", style="bold green")
    
    layout = make_layout()
    
    with Live(layout, refresh_per_second=1, screen=True) as live:
        while True:
            data = fetch_data()
            update_layout(layout, data)
            time.sleep(REFRESH_RATE)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nUsing Dashboard Closed.")
        sys.exit(0)
