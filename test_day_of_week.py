#!/usr/bin/env python3

import sys
import os
import json
from datetime import datetime

# Add the python-api directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

# Import the functions from main.py
from main import calculate_supertrend_weekly, calculate_weekly_monthly_ohlcv, get_week_start_timestamp

def test_day_of_week_logic():
    """Test weekly aggregation with proper day-of-week logic"""
    
    # Load real WORTH data
    with open('db/WORTH.json', 'r') as f:
        worth_data = json.load(f)
    
    # Use the last 120 days to ensure we have enough weekly candles for SuperTrend calculation (need 10+ weeks)
    recent_data = worth_data[-120:]
    print(f"Testing day-of-week logic with last {len(recent_data)} daily candles")
    
    # Show daily data with day of week
    print("\n=== DAILY DATA WITH DAY OF WEEK ===")
    for i, candle in enumerate(recent_data[-10:]):  # Show last 10 days
        timestamp = candle.get("timestamp", 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        day_of_week = dt.strftime('%A')
        date_str = dt.strftime('%Y-%m-%d')
        
        print(f"{date_str} ({day_of_week}): O={candle.get('open'):.2f} H={candle.get('high'):.2f} L={candle.get('low'):.2f} C={candle.get('close'):.2f}")
    
    # Calculate weekly OHLCV with new logic
    weekly_ohlcv, _ = calculate_weekly_monthly_ohlcv(recent_data)
    
    print(f"\n=== WEEKLY AGGREGATION RESULTS ===")
    print(f"Generated {len(weekly_ohlcv)} weekly candles")
    
    # Show weekly data with day information
    for i, (week_key, weekly_candle) in enumerate(sorted(weekly_ohlcv.items())[-5:]):  # Show last 5 weeks
        week_dt = datetime.fromtimestamp(week_key / 1000)
        week_str = week_dt.strftime('%Y-%m-%d')
        days_included = weekly_candle.get("days", [])
        count = weekly_candle.get("count", 0)
        
        print(f"\nWeek starting {week_str}:")
        print(f"  Days included: {', '.join(days_included)} ({count} days)")
        print(f"  OHLC: O={weekly_candle['open']:.2f} H={weekly_candle['high']:.2f} L={weekly_candle['low']:.2f} C={weekly_candle['close']:.2f}")
        print(f"  Volume: {weekly_candle['volume']:.0f}")
    
    # Test SuperTrend calculation with new weekly data
    print(f"\n=== WEEKLY SUPERTREND WITH DAY-OF-WEEK LOGIC ===")
    
    # Convert to sorted list for SuperTrend calculation
    weekly_candles = []
    for week_key in sorted(weekly_ohlcv.keys()):
        weekly_candles.append(weekly_ohlcv[week_key])
    
    weekly_highs = [float(candle.get("high", 0)) for candle in weekly_candles]
    weekly_lows = [float(candle.get("low", 0)) for candle in weekly_candles]
    weekly_closes = [float(candle.get("close", 0)) for candle in weekly_candles]
    
    # Calculate weekly SuperTrend
    weekly_supertrend = calculate_supertrend_weekly(weekly_highs, weekly_lows, weekly_closes, period=10, multiplier=2)
    
    print("Last 5 weekly SuperTrend values:")
    expected_values = [132.88, 167.72, 169.90, 173.57, 176.01]
    
    for i in range(min(5, len(weekly_supertrend))):
        if len(weekly_supertrend) > i:
            index = len(weekly_supertrend) - 1 - i
            week_key = sorted(weekly_ohlcv.keys())[index]
            date_str = datetime.fromtimestamp(week_key / 1000).strftime('%Y-%m-%d')
            close = weekly_closes[index]
            supertrend_val = weekly_supertrend[index]
            weeks_ago = i
            
            days_in_week = weekly_ohlcv[week_key].get("days", [])
            expected = expected_values[i] if i < len(expected_values) else "N/A"
            
            if supertrend_val is not None:
                diff = abs(supertrend_val - expected) if isinstance(expected, (int, float)) else "N/A"
                print(f"  {weeks_ago} weeks ago ({date_str}): Days={days_in_week} Close={close:.2f}, SuperTrend={supertrend_val:.2f}, Expected={expected}, Diff={diff}")
            else:
                print(f"  {weeks_ago} weeks ago ({date_str}): Days={days_in_week} Close={close:.2f}, SuperTrend=None, Expected={expected}")
    
    print(f"\nEXPECTED VALUES:")
    print("Today (0 weeks ago): 132.88")
    print("1 week ago: 167.72")
    print("2 weeks ago: 169.90")
    print("3 weeks ago: 173.57")
    print("4 weeks ago: 176.01")

if __name__ == "__main__":
    test_day_of_week_logic()