#!/usr/bin/env python3

import csv
import sys
import os

def compare_with_debug():
    """Compare current results with debug.csv to find missing stocks"""
    
    print('Comparing current results with debug.csv...')
    
    # Read debug.csv stocks
    debug_stocks = set()
    try:
        with open('debug.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row['Symbol'].strip()
                debug_stocks.add(symbol)
        
        print(f'Debug.csv has {len(debug_stocks)} stocks')
    except Exception as e:
        print(f'Error reading debug.csv: {e}')
        return
    
    # Read current results
    current_stocks = set()
    try:
        with open('current_400_results.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row['stock'].strip()
                current_stocks.add(symbol)
        
        print(f'Current results have {len(current_stocks)} stocks')
    except Exception as e:
        print(f'Error reading current_400_results.csv: {e}')
        return
    
    # Find differences
    missing_from_current = debug_stocks - current_stocks
    extra_in_current = current_stocks - debug_stocks
    
    print(f'\\n=== COMPARISON RESULTS ===')
    print(f'Expected stocks (debug.csv): {len(debug_stocks)}')
    print(f'Current stocks: {len(current_stocks)}')
    print(f'Missing from current: {len(missing_from_current)}')
    print(f'Extra in current: {len(extra_in_current)}')
    
    if missing_from_current:
        print(f'\\nMISSING STOCKS (should be included but not found):')
        for stock in sorted(missing_from_current):
            print(f'  {stock}')
    
    if extra_in_current:
        print(f'\\nEXTRA STOCKS (found but not in debug.csv):')
        for stock in sorted(extra_in_current):
            print(f'  {stock}')
    
    # Show some common stocks for verification
    common_stocks = debug_stocks & current_stocks
    print(f'\\nCommon stocks: {len(common_stocks)}')
    if len(common_stocks) > 0:
        print('First 5 common stocks:', sorted(list(common_stocks))[:5])
    
    return missing_from_current, extra_in_current

if __name__ == "__main__":
    compare_with_debug()