#!/usr/bin/env python3
"""
Live Timer Demo for Latest Candle Updates

This script shows a live countdown timer in the terminal, displaying:
- Current time
- Market status (Open/Closed)
- Time until next update
- Last update status
- Real-time countdown

Usage: python live_timer_demo.py
"""

import asyncio
import sys
import os
from datetime import datetime, time, timedelta
from pathlib import Path
import requests
import json

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.latest_candle_updater import latest_candle_updater

class LiveTimer:
    def __init__(self):
        self.update_interval = 2  # minutes
        self.last_update_time = None
        self.last_update_status = "Not started"
        self.is_scheduler_running = False
        self.api_base = "http://127.0.0.1:8001"
        
    def is_market_hours(self):
        """Check if current time is within market hours."""
        now = datetime.now()
        current_time = now.time()
        
        # Market hours: 9:15 AM to 3:30 PM IST
        market_open = time(9, 15)
        market_close = time(15, 30)
        
        # Skip weekends
        if now.weekday() >= 5:
            return False
            
        return market_open <= current_time <= market_close
    
    def get_next_update_time(self):
        """Calculate when the next update should occur."""
        now = datetime.now()
        
        if self.last_update_time is None:
            # If no previous update, next update is in 2 minutes
            return now + timedelta(minutes=self.update_interval)
        
        # Next update is 2 minutes after last update
        return self.last_update_time + timedelta(minutes=self.update_interval)
    
    def get_market_status_display(self):
        """Get colored market status display."""
        if self.is_market_hours():
            return "\033[92m●\033[0m MARKET OPEN"  # Green dot
        else:
            return "\033[91m●\033[0m MARKET CLOSED"  # Red dot
    
    def get_scheduler_status(self):
        """Check if scheduler is running via API."""
        try:
            response = requests.get(f"{self.api_base}/api/periodic-updates-status", timeout=2)
            if response.status_code == 200:
                data = response.json()
                return data.get('is_running', False)
        except:
            pass
        return False
    
    def format_time_remaining(self, seconds):
        """Format seconds into a readable countdown."""
        if seconds <= 0:
            return "00:00"
        
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    async def start_scheduler_if_needed(self):
        """Start the scheduler if it's not running."""
        if not self.get_scheduler_status():
            try:
                response = requests.post(f"{self.api_base}/api/start-periodic-updates")
                if response.status_code == 200:
                    self.last_update_status = "Scheduler started"
                    return True
            except:
                pass
        return False
    
    async def run_timer(self):
        """Run the live timer display."""
        print("Starting Live Timer Demo...")
        print("Press Ctrl+C to stop")
        await asyncio.sleep(2)
        
        while True:
            try:
                # Clear screen for live update effect
                self.clear_screen()
                
                now = datetime.now()
                next_update = self.get_next_update_time()
                time_until_next = (next_update - now).total_seconds()
                
                # Check scheduler status
                scheduler_running = self.get_scheduler_status()
                
                # Auto-start scheduler during market hours
                if self.is_market_hours() and not scheduler_running:
                    await self.start_scheduler_if_needed()
                    scheduler_running = True
                
                # Display header
                print("="*80)
                print("🕒 LATEST CANDLE UPDATE - LIVE TIMER")
                print("="*80)
                print()
                
                # Current time and market status
                print(f"⏰ Current Time:     {now.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"📈 Market Status:    {self.get_market_status_display()}")
                print()
                
                # Scheduler status
                scheduler_color = "\033[92m" if scheduler_running else "\033[91m"  # Green/Red
                scheduler_status = "RUNNING" if scheduler_running else "STOPPED"
                print(f"🔄 Scheduler:        {scheduler_color}●\033[0m {scheduler_status}")
                print(f"⚡ Update Interval:  Every {self.update_interval} minutes")
                print()
                
                # Next update countdown
                if time_until_next > 0 and scheduler_running and self.is_market_hours():
                    countdown = self.format_time_remaining(time_until_next)
                    print(f"⏳ Next Update In:   \033[93m{countdown}\033[0m")
                    
                    # Progress bar
                    total_seconds = self.update_interval * 60
                    elapsed_seconds = total_seconds - time_until_next
                    progress = max(0, min(1, elapsed_seconds / total_seconds))
                    bar_length = 40
                    filled_length = int(bar_length * progress)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    percentage = int(progress * 100)
                    print(f"📊 Progress:         [{bar}] {percentage}%")
                    
                elif not self.is_market_hours():
                    print(f"⏳ Next Update In:   \033[90mWaiting for market hours\033[0m")
                    
                    # Show time until market opens
                    tomorrow = now.replace(hour=9, minute=15, second=0, microsecond=0)
                    if now.time() > time(15, 30):  # After market close
                        tomorrow += timedelta(days=1)
                    
                    # Skip weekends
                    while tomorrow.weekday() >= 5:
                        tomorrow += timedelta(days=1)
                    
                    time_to_market = (tomorrow - now).total_seconds()
                    hours_to_market = int(time_to_market // 3600)
                    mins_to_market = int((time_to_market % 3600) // 60)
                    print(f"🌅 Market Opens In:  {hours_to_market}h {mins_to_market}m")
                    
                elif not scheduler_running:
                    print(f"⏳ Next Update In:   \033[90mScheduler not running\033[0m")
                    
                else:
                    print(f"⏳ Next Update In:   \033[93mStarting...\033[0m")
                
                print()
                
                # Last update info
                if self.last_update_time:
                    time_ago = (now - self.last_update_time).total_seconds()
                    if time_ago < 60:
                        time_ago_str = f"{int(time_ago)}s ago"
                    else:
                        time_ago_str = f"{int(time_ago // 60)}m {int(time_ago % 60)}s ago"
                    
                    print(f"✅ Last Update:      {self.last_update_time.strftime('%H:%M:%S')} ({time_ago_str})")
                else:
                    print(f"✅ Last Update:      Not yet")
                
                print(f"📝 Status:           {self.last_update_status}")
                print()
                
                # Instructions
                print("="*80)
                print("💡 INSTRUCTIONS:")
                print("   • Timer updates every second")
                print("   • Updates only run during market hours (9:15 AM - 3:30 PM)")
                print("   • Scheduler auto-starts during market hours")
                print("   • Press Ctrl+C to stop")
                print("="*80)
                
                # Update last update time if we detect an update happened
                # (This is a simple demo - in real scenario you'd get this from API)
                if time_until_next <= 0 and scheduler_running and self.is_market_hours():
                    self.last_update_time = now
                    self.last_update_status = "Updated successfully"
                
                # Wait 1 second before next refresh
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in timer: {e}")
                await asyncio.sleep(1)

async def main():
    """Main function."""
    timer = LiveTimer()
    
    try:
        await timer.run_timer()
    except KeyboardInterrupt:
        print("\n\n🛑 Timer stopped by user")
        print("Goodbye!")
    except Exception as e:
        print(f"\n❌ Timer error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Failed to start timer: {e}")