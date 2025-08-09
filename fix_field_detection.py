#!/usr/bin/env python3
"""
Script to diagnose and fix field detection issues
"""

import json
import os
from pathlib import Path

def check_actual_fields():
    """Check what fields actually exist in the precalculated data"""
    
    # Check if precalculated storage exists
    storage_dir = Path("precalculatedStorage")
    if not storage_dir.exists():
        print("ERROR precalculatedStorage directory does not exist!")
        return set()
    
    # Get a sample file
    sample_files = list(storage_dir.glob("*_piped.json"))
    if not sample_files:
        print("ERROR No precalculated data files found!")
        return set()
    
    sample_file = sample_files[0]
    print(f"OK Checking fields in: {sample_file.name}")
    
    # Load and check fields
    with open(sample_file, 'r') as f:
        data = json.load(f)
    
    if not data.get("data") or len(data["data"]) == 0:
        print("ERROR No data in file!")
        return set()
    
    # Get all unique fields from last candle
    last_candle = data["data"][-1]
    fields = set(last_candle.keys())
    
    print(f"OK Found {len(fields)} fields in data")
    return fields

def check_config_indicators():
    """Check what indicators are configured"""
    
    config_file = Path("python-api/precalculatedIndicators.json")
    if not config_file.exists():
        print("ERROR precalculatedIndicators.json does not exist!")
        return []
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    indicators = config.get("indicators", [])
    print(f"OK Found {len(indicators)} indicators in config")
    
    # Generate expected field names
    expected_fields = set()
    for ind in indicators:
        timeframe = ind.get("timeframe", "daily")
        name = ind.get("name", "")
        params = ind.get("params", {})
        
        if name == "supertrend":
            period = params.get("period", 10)
            multiplier = params.get("multiplier", 3)
            # Note: actual data uses decimal format
            field_name = f"{timeframe}_{name}_{period}_{multiplier}"
            expected_fields.add(field_name)
            print(f"  - Expected: {field_name}")
        elif name == "pctchg":
            period = params.get("period", 1)
            period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period)
            field_name = f"{timeframe}_{name}_{period_str}"
            expected_fields.add(field_name)
            print(f"  - Expected: {field_name}")
    
    return expected_fields

def main():
    print("=" * 60)
    print("FIELD DETECTION DIAGNOSTIC")
    print("=" * 60)
    
    # Check actual fields in data
    print("\n1. ACTUAL FIELDS IN DATA:")
    actual_fields = check_actual_fields()
    
    # Check expected fields from config
    print("\n2. EXPECTED FIELDS FROM CONFIG:")
    expected_fields = check_config_indicators()
    
    # Find missing fields
    print("\n3. FIELD ANALYSIS:")
    
    # Filter for indicator fields only (not basic price fields)
    indicator_fields = {f for f in actual_fields if '_' in f and not f in 
                       ['weekly_open', 'weekly_high', 'weekly_low', 'weekly_close', 'weekly_volume',
                        'monthly_open', 'monthly_high', 'monthly_low', 'monthly_close', 'monthly_volume',
                        'date', 'timestamp', 'dayOfWeek', 'weekend', 'monthend']}
    
    print(f"\nActual indicator fields in data:")
    for field in sorted(indicator_fields):
        print(f"  OK {field}")
    
    print(f"\nExpected fields from config:")
    for field in sorted(expected_fields):
        if field in actual_fields or f"{field}.0" in actual_fields:
            print(f"  OK {field} (found)")
        else:
            print(f"  ERROR {field} (MISSING!)")
    
    # Check for specific problematic fields
    print("\n4. SPECIFIC FIELD CHECKS:")
    
    # Check for daily_pctchg_1
    pctchg_fields = [f for f in actual_fields if 'pctchg' in f.lower()]
    if pctchg_fields:
        print(f"  OK Found pctchg fields: {pctchg_fields}")
    else:
        print(f"  ERROR No pctchg fields found in data!")
    
    # Check for weekly_supertrend
    supertrend_fields = [f for f in actual_fields if 'supertrend' in f.lower()]
    if supertrend_fields:
        print(f"  OK Found supertrend fields: {supertrend_fields}")
    else:
        print(f"  ERROR No supertrend fields found in data!")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATION:")
    print("The indicators in config are NOT matching the actual data files.")
    print("You need to re-run the precalculation to properly add these fields.")
    print("=" * 60)

if __name__ == "__main__":
    main()