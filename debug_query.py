#!/usr/bin/env python3
"""
Debug script to test query evaluation for AGROPHOS bug.
This script tests the specific condition "daily_pctchg_1 < 9 and daily_pctchg_1 > 0"
and checks if AGROPHOS incorrectly passes the positive condition.
"""

import json
import sys
import os

# Add the python-api directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

from services.query_service import parse_query, find_matching_candles

def load_agrophos_data():
    """Load AGROPHOS data from the precalculated storage."""
    with open('precalculatedStorage/AGROPHOS_piped.json', 'r') as f:
        data = json.load(f)
    return data['data']

def test_query_conditions():
    """Test the specific query conditions that are failing."""
    
    print("=== DEBUGGING AGROPHOS QUERY EVALUATION ===")
    print()
    
    # Load AGROPHOS data
    candles = load_agrophos_data()
    print(f"Loaded {len(candles)} candles for AGROPHOS")
    
    # Find the candle with negative daily_pctchg_1
    negative_candle = None
    negative_index = -1
    for i, candle in enumerate(candles):
        if candle.get('daily_pctchg_1') == -0.4527960153950709:
            negative_candle = candle
            negative_index = i
            break
    
    if negative_candle:
        print(f"Found negative percentage candle at index {negative_index}:")
        print(f"  daily_pctchg_1: {negative_candle['daily_pctchg_1']}")
        print(f"  timestamp: {negative_candle.get('timestamp')}")
        print(f"  close: {negative_candle.get('close')}")
    else:
        print("ERROR: Could not find candle with daily_pctchg_1 = -0.4527960153950709")
        return
    
    print()
    
    # Test queries
    test_queries = [
        "daily_pctchg_1 > 0",  # Should NOT match AGROPHOS negative candle
        "daily_pctchg_1 < 0",  # Should match AGROPHOS negative candle
        "daily_pctchg_1 < 9 and daily_pctchg_1 > 0"  # Should NOT match AGROPHOS negative candle
    ]
    
    for query_str in test_queries:
        print(f"Testing query: '{query_str}'")
        
        # Parse the query
        parsed_query = parse_query(query_str)
        print(f"  Parsed conditions: {len(parsed_query.get('conditions', []))}")
        for i, condition in enumerate(parsed_query.get('conditions', [])):
            print(f"    Condition {i+1}: {condition['left']['field']} {condition['operator']} {condition['right']['value']}")
        
        # Find matches
        matches = find_matching_candles(candles, parsed_query, "AGROPHOS")
        print(f"  Total matches: {len(matches)}")
        
        # Check if our negative candle is in the matches
        negative_candle_matched = False
        for match in matches:
            if match.get('daily_pctchg_1') == -0.4527960153950709:
                negative_candle_matched = True
                break
        
        print(f"  Negative candle matched: {negative_candle_matched}")
        
        # This is the bug check
        if query_str in ["daily_pctchg_1 > 0", "daily_pctchg_1 < 9 and daily_pctchg_1 > 0"]:
            if negative_candle_matched:
                print(f"  [BUG] FOUND: Negative percentage candle incorrectly matched positive condition!")
            else:
                print(f"  [OK] Correct: Negative percentage candle did not match positive condition")
        elif query_str == "daily_pctchg_1 < 0":
            if negative_candle_matched:
                print(f"  [OK] Correct: Negative percentage candle matched negative condition")
            else:
                print(f"  [BUG] FOUND: Negative percentage candle should have matched negative condition!")
        
        print()

if __name__ == "__main__":
    test_query_conditions()