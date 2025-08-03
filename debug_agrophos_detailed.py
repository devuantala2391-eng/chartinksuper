#!/usr/bin/env python3
"""
Detailed debug script to analyze AGROPHOS data for the reported bug.
"""

import json
import sys
import os

def analyze_agrophos_data():
    """Analyze AGROPHOS data in detail."""
    
    print("=== DETAILED AGROPHOS ANALYSIS ===")
    print()
    
    # Load AGROPHOS data
    with open('precalculatedStorage/AGROPHOS_piped.json', 'r') as f:
        data = json.load(f)
    
    candles = data['data']
    print(f"Total candles: {len(candles)}")
    
    # Analyze daily_pctchg_1 values
    positive_count = 0
    negative_count = 0
    zero_count = 0
    null_count = 0
    
    positive_candles = []
    negative_candles = []
    
    for i, candle in enumerate(candles):
        pctchg = candle.get('daily_pctchg_1')
        
        if pctchg is None:
            null_count += 1
        elif pctchg > 0:
            positive_count += 1
            positive_candles.append((i, pctchg, candle.get('timestamp'), candle.get('close')))
        elif pctchg < 0:
            negative_count += 1
            negative_candles.append((i, pctchg, candle.get('timestamp'), candle.get('close')))
        else:  # pctchg == 0
            zero_count += 1
    
    print(f"Positive daily_pctchg_1: {positive_count}")
    print(f"Negative daily_pctchg_1: {negative_count}")
    print(f"Zero daily_pctchg_1: {zero_count}")
    print(f"Null daily_pctchg_1: {null_count}")
    print()
    
    # Show the specific negative candle mentioned by user
    target_value = -0.4527960153950709
    print(f"Looking for candle with daily_pctchg_1 = {target_value}")
    
    target_candle = None
    for i, candle in enumerate(candles):
        if candle.get('daily_pctchg_1') == target_value:
            target_candle = (i, candle)
            print(f"Found at index {i}:")
            print(f"  timestamp: {candle.get('timestamp')}")
            print(f"  date: {candle.get('date')}")
            print(f"  dayOfWeek: {candle.get('dayOfWeek')}")
            print(f"  close: {candle.get('close')}")
            print(f"  daily_pctchg_1: {candle.get('daily_pctchg_1')}")
            break
    
    if not target_candle:
        print("Target candle not found!")
        return
    
    print()
    
    # Show last few candles to see latest data
    print("Last 5 candles:")
    for i in range(max(0, len(candles) - 5), len(candles)):
        candle = candles[i]
        print(f"  [{i}] daily_pctchg_1: {candle.get('daily_pctchg_1')}, close: {candle.get('close')}, timestamp: {candle.get('timestamp')}")
    
    print()
    
    # Check if there are any candles with similar values that might cause confusion
    print("Candles with daily_pctchg_1 between -1 and 1:")
    for i, candle in enumerate(candles):
        pctchg = candle.get('daily_pctchg_1')
        if pctchg is not None and -1 <= pctchg <= 1:
            print(f"  [{i}] daily_pctchg_1: {pctchg}, close: {candle.get('close')}")
    
    print()
    
    # Show conditions that would match the target candle
    target_pctchg = target_candle[1].get('daily_pctchg_1')
    print(f"Target candle daily_pctchg_1: {target_pctchg}")
    print("This candle should match:")
    print(f"  daily_pctchg_1 < 0: {target_pctchg < 0}")  # True
    print(f"  daily_pctchg_1 > 0: {target_pctchg > 0}")  # False
    print(f"  daily_pctchg_1 < 9: {target_pctchg < 9}")  # True
    print(f"  daily_pctchg_1 < 9 AND daily_pctchg_1 > 0: {target_pctchg < 9 and target_pctchg > 0}")  # False

if __name__ == "__main__":
    analyze_agrophos_data()