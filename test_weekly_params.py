#!/usr/bin/env python3

import sys
import os
import json
from datetime import datetime

# Add the python-api directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

# Import the functions from main.py
from main import calculate_supertrend_weekly, calculate_weekly_monthly_ohlcv, calculate_supertrend

def test_weekly_parameters():
    """Test different parameters for weekly SuperTrend to match expected values"""
    
    # Load real WORTH data
    with open('db/WORTH.json', 'r') as f:
        worth_data = json.load(f)
    
    # Use the last 120 days to ensure we have enough weekly candles
    recent_data = worth_data[-120:]
    
    # Calculate weekly OHLCV with day-of-week logic
    weekly_ohlcv, _ = calculate_weekly_monthly_ohlcv(recent_data)
    
    # Convert to sorted list for SuperTrend calculation
    weekly_candles = []
    for week_key in sorted(weekly_ohlcv.keys()):
        weekly_candles.append(weekly_ohlcv[week_key])
    
    weekly_highs = [float(candle.get("high", 0)) for candle in weekly_candles]
    weekly_lows = [float(candle.get("low", 0)) for candle in weekly_candles]
    weekly_closes = [float(candle.get("close", 0)) for candle in weekly_candles]
    
    expected_values = [132.88, 167.72, 169.90, 173.57, 176.01]
    
    print("Testing different parameter combinations for weekly SuperTrend:")
    print("Expected values: Today=132.88, 1w=167.72, 2w=169.90, 3w=173.57, 4w=176.01")
    print()
    
    # Test different combinations
    test_params = [
        {"period": 10, "multiplier": 2, "desc": "Current"},
        {"period": 10, "multiplier": 1.8, "desc": "Lower multiplier"},
        {"period": 10, "multiplier": 1.5, "desc": "Much lower multiplier"},
        {"period": 14, "multiplier": 2, "desc": "Higher period"},
        {"period": 7, "multiplier": 2, "desc": "Lower period"},
        {"period": 10, "multiplier": 2.5, "desc": "Higher multiplier"},
    ]
    
    for params in test_params:
        print(f"=== {params['desc']} (period={params['period']}, multiplier={params['multiplier']}) ===")
        
        weekly_supertrend = calculate_supertrend_weekly(weekly_highs, weekly_lows, weekly_closes, 
                                                      period=params['period'], multiplier=params['multiplier'])
        
        if len(weekly_supertrend) >= 5:
            total_diff = 0
            for i in range(5):
                index = len(weekly_supertrend) - 1 - i
                supertrend_val = weekly_supertrend[index]
                expected = expected_values[i]
                
                if supertrend_val is not None:
                    diff = abs(supertrend_val - expected)
                    total_diff += diff
                    print(f"  {i}w ago: {supertrend_val:.2f} (expected {expected}, diff {diff:.2f})")
                else:
                    print(f"  {i}w ago: None (expected {expected})")
            
            print(f"  Total difference: {total_diff:.2f}")
        else:
            print("  Not enough data for calculation")
        print()
    
    # Also test with the daily SuperTrend function to see if it gives different results
    print("=== Testing with Daily SuperTrend Function on Weekly Data ===")
    daily_on_weekly = calculate_supertrend(weekly_highs, weekly_lows, weekly_closes, period=10, multiplier=2)
    
    if len(daily_on_weekly) >= 5:
        total_diff = 0
        for i in range(5):
            index = len(daily_on_weekly) - 1 - i
            supertrend_val = daily_on_weekly[index]
            expected = expected_values[i]
            
            if supertrend_val is not None:
                diff = abs(supertrend_val - expected)
                total_diff += diff
                print(f"  {i}w ago: {supertrend_val:.2f} (expected {expected}, diff {diff:.2f})")
            else:
                print(f"  {i}w ago: None (expected {expected})")
        
        print(f"  Total difference: {total_diff:.2f}")

if __name__ == "__main__":
    test_weekly_parameters()