#!/usr/bin/env python3
"""
Test script to verify the fallback find_matching_candles bug fix.
"""

import json

def test_fallback_implementation():
    """Test the fallback find_matching_candles implementation with AGROPHOS data."""
    
    print("=== TESTING FALLBACK IMPLEMENTATION FIX ===")
    print()
    
    # Load AGROPHOS data
    with open('precalculatedStorage/AGROPHOS_piped.json', 'r') as f:
        data = json.load(f)
    
    candles = data['data']
    
    # Find the candle with negative daily_pctchg_1
    target_candle = None
    for candle in candles:
        if candle.get('daily_pctchg_1') == -0.4527960153950709:
            target_candle = candle
            break
    
    if not target_candle:
        print("ERROR: Could not find target candle")
        return
    
    print(f"Target candle daily_pctchg_1: {target_candle['daily_pctchg_1']}")
    print()
    
    # Test the fallback implementation logic manually
    test_conditions = [
        {
            "left": {"type": "field", "field": "daily_pctchg_1"},
            "operator": ">",
            "right": {"type": "value", "value": 0}
        },
        {
            "left": {"type": "field", "field": "daily_pctchg_1"},
            "operator": "<",
            "right": {"type": "value", "value": 9}
        }
    ]
    
    # Test each condition individually
    for i, condition in enumerate(test_conditions):
        left = condition["left"]
        operator = condition["operator"]
        right = condition["right"]
        
        print(f"Testing condition {i+1}: daily_pctchg_1 {operator} {right['value']}")
        
        # Apply the FIXED logic
        if left.get("type") == "field":
            left_field = left.get("field", "")
            left_raw = target_candle.get(left_field)
            left_val = float(left_raw) if left_raw is not None else None
        else:
            left_val = float(left.get("value", 0))
        
        if right.get("type") == "field":
            right_field = right.get("field", "")
            right_raw = target_candle.get(right_field)
            right_val = float(right_raw) if right_raw is not None else None
        else:
            right_val = float(right.get("value", 0))
        
        print(f"  left_val: {left_val}")
        print(f"  right_val: {right_val}")
        
        if left_val is None or right_val is None:
            result = False
            print(f"  result: {result} (None value)")
        else:
            if operator == ">":
                result = left_val > right_val
            elif operator == "<":
                result = left_val < right_val
            elif operator == ">=":
                result = left_val >= right_val
            elif operator == "<=":
                result = left_val <= right_val
            elif operator == "==":
                result = left_val == right_val
            else:
                result = False
            
            print(f"  result: {result}")
        
        print()
    
    # Test the combined condition: daily_pctchg_1 < 9 AND daily_pctchg_1 > 0
    print("Testing combined condition: daily_pctchg_1 < 9 AND daily_pctchg_1 > 0")
    
    results = []
    for condition in test_conditions:
        left = condition["left"]
        operator = condition["operator"]
        right = condition["right"]
        
        # Apply the FIXED logic
        if left.get("type") == "field":
            left_field = left.get("field", "")
            left_raw = target_candle.get(left_field)
            left_val = float(left_raw) if left_raw is not None else None
        else:
            left_val = float(left.get("value", 0))
        
        if right.get("type") == "field":
            right_field = right.get("field", "")
            right_raw = target_candle.get(right_field)
            right_val = float(right_raw) if right_raw is not None else None
        else:
            right_val = float(right.get("value", 0))
        
        if left_val is None or right_val is None:
            result = False
        else:
            if operator == ">":
                result = left_val > right_val
            elif operator == "<":
                result = left_val < right_val
            elif operator == ">=":
                result = left_val >= right_val
            elif operator == "<=":
                result = left_val <= right_val
            elif operator == "==":
                result = left_val == right_val
            else:
                result = False
        
        results.append(result)
    
    # Combined result with AND logic
    final_result = all(results)
    print(f"  Individual results: {results}")
    print(f"  Combined result (AND): {final_result}")
    
    if final_result:
        print("  [BUG] FOUND: AGROPHOS negative candle incorrectly matches positive condition!")
    else:
        print("  [OK] Correct: AGROPHOS negative candle does not match positive condition")

if __name__ == "__main__":
    test_fallback_implementation()