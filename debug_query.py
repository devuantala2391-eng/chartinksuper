#!/usr/bin/env python3
"""Debug why pctchg query returns 0 matches"""

import json
from pathlib import Path
import sys
sys.path.append('python-api')

from services.query_service import parse_query, find_matching_candles

# Load a stock that we know has positive pctchg
stock_file = Path('python-api/precalculatedStorage/SHYAMCENT_piped.json')
with open(stock_file, 'r') as f:
    data = json.load(f)

candles = data['data']
last_candle = candles[-1]

print(f"Stock: SHYAMCENT")
print(f"Last candle daily_pctchg_1: {last_candle.get('daily_pctchg_1')}")

# Test query
query = "daily_pctchg_1 > 0"
parsed = parse_query(query)
print(f"\nQuery: {query}")
print(f"Parsed: {parsed}")

# Try to find matches
matches = find_matching_candles(candles[-2:], parsed, "SHYAMCENT")
print(f"\nMatches found: {len(matches)}")

if matches:
    print("Match details:", matches[0])
else:
    print("No matches - debugging...")
    
    # Manually check the condition
    from services.query_service import get_field_value
    
    last_two = candles[-2:]
    for i, candle in enumerate(last_two):
        val = get_field_value(candle, 'daily_pctchg_1', last_two, i)
        print(f"Candle {i}: daily_pctchg_1 = {val}")