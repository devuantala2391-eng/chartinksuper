"""
Test script to demonstrate cron job environment variable controls
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_cron_env_controls():
    print("=== CRON JOB ENVIRONMENT CONTROLS ===")
    print()

    # Import the configuration functions
    from services.latest_candle_updater import (
        get_latest_candle_cron_enabled,
        get_latest_candle_cron_interval,
        get_latest_candle_market_hours_only,
        get_latest_candle_debug_timer
    )

    # Show current settings
    print("Current .env settings:")
    print(f"  LATEST_CANDLE_CRON_ENABLED = {os.getenv('LATEST_CANDLE_CRON_ENABLED', 'NOT SET')}")
    print(f"  LATEST_CANDLE_CRON_INTERVAL = {os.getenv('LATEST_CANDLE_CRON_INTERVAL', 'NOT SET')}")
    print(f"  LATEST_CANDLE_MARKET_HOURS_ONLY = {os.getenv('LATEST_CANDLE_MARKET_HOURS_ONLY', 'NOT SET')}")
    print(f"  LATEST_CANDLE_DEBUG_TIMER = {os.getenv('LATEST_CANDLE_DEBUG_TIMER', 'NOT SET')}")
    print()

    # Show parsed values
    print("Parsed configuration:")
    print(f"  Cron Enabled: {get_latest_candle_cron_enabled()}")
    print(f"  Cron Interval: {get_latest_candle_cron_interval()} minutes")
    print(f"  Market Hours Only: {get_latest_candle_market_hours_only()}")
    print(f"  Debug Timer: {get_latest_candle_debug_timer()}")
    print()

    # Show how to control the cron job
    print("=== HOW TO CONTROL CRON JOB ===")
    print()
    print("To DISABLE the cron job:")
    print("  Set LATEST_CANDLE_CRON_ENABLED=false in .env file")
    print()
    print("To change update frequency:")
    print("  Set LATEST_CANDLE_CRON_INTERVAL=5 (for 5 minutes)")
    print()
    print("To run only during market hours:")
    print("  Set LATEST_CANDLE_MARKET_HOURS_ONLY=true")
    print()
    print("To disable debug console output:")
    print("  Set LATEST_CANDLE_DEBUG_TIMER=false")
    print()
    print("After changing .env, restart the server for changes to take effect.")

if __name__ == "__main__":
    test_cron_env_controls()