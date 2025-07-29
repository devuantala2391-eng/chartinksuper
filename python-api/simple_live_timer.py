#!/usr/bin/env python3
"""
Simple Live Timer - Guaranteed to work in terminal
"""

import time
import os
import sys
from datetime import datetime, timedelta

def clear_screen():
    """Clear terminal screen"""
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:  # Unix/Linux/Mac
        os.system('clear')

def is_market_open():
    """Check if market is currently open"""
    now = datetime.now()
    current_time = now.time()
    
    # Skip weekends
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    # Market hours: 9:15 AM to 3:30 PM
    market_open = datetime.strptime('09:15', '%H:%M').time()
    market_close = datetime.strptime('15:30', '%H:%M').time()
    
    return market_open <= current_time <= market_close

def main():
    """Main timer loop"""
    print("Starting Live Timer...")
    time.sleep(1)
    
    update_interval_seconds = 2 * 60  # 2 minutes = 120 seconds
    start_time = time.time()
    
    try:
        while True:
            clear_screen()
            
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Calculate next update
            cycle_position = elapsed % update_interval_seconds
            time_to_next_update = update_interval_seconds - cycle_position
            
            # Format time
            now = datetime.now()
            minutes_left = int(time_to_next_update // 60)
            seconds_left = int(time_to_next_update % 60)
            
            # Market status
            market_status = "🟢 OPEN" if is_market_open() else "🔴 CLOSED"
            
            # Progress calculation
            progress_percent = (cycle_position / update_interval_seconds) * 100
            progress_bars = int(progress_percent / 2.5)  # 40 bars total
            progress_bar = "█" * progress_bars + "░" * (40 - progress_bars)
            
            # Display
            print("=" * 60)
            print("🕒 LATEST CANDLE UPDATE - LIVE TIMER")
            print("=" * 60)
            print()
            print(f"⏰ Current Time:    {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📈 Market Status:   {market_status}")
            print(f"⚡ Update Every:    2 minutes")
            print()
            print(f"⏳ Next Update:     {minutes_left:02d}:{seconds_left:02d}")
            print(f"📊 Progress:        [{progress_bar}] {int(progress_percent)}%")
            print()
            
            if is_market_open():
                print("✅ Status: Active - Updates will run")
            else:
                print("⏸️  Status: Waiting for market hours (9:15 AM - 3:30 PM)")
            
            print()
            print("Press Ctrl+C to stop")
            print("=" * 60)
            
            # Sleep for 1 second before next update
            time.sleep(1)
            
    except KeyboardInterrupt:
        clear_screen()
        print("\n🛑 Timer stopped!")
        print("Goodbye! 👋")
        sys.exit(0)

if __name__ == "__main__":
    main()