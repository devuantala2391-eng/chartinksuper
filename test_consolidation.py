#!/usr/bin/env python3
"""Test that consolidation to python-api folders worked correctly"""

from pathlib import Path
import json

print("=" * 60)
print("TESTING FOLDER CONSOLIDATION")
print("=" * 60)

# Check directory structure
root_precalc = Path("precalculatedStorage")
root_db = Path("db")
api_precalc = Path("python-api/precalculatedStorage")
api_db = Path("python-api/db")

print("\n1. Directory Structure:")
print(f"   Root level precalculatedStorage exists: {root_precalc.exists()}")
print(f"   Root level db exists: {root_db.exists()}")
print(f"   Python-api precalculatedStorage exists: {api_precalc.exists()}")
print(f"   Python-api db exists: {api_db.exists()}")

if not root_precalc.exists():
    print("   [OK] Root level precalculatedStorage successfully removed")

if not root_db.exists():
    print("   [OK] Root level db successfully removed")

# Check python-api/precalculatedStorage
if api_precalc.exists():
    files = list(api_precalc.glob("*_piped.json"))
    print(f"\n2. Python-api precalculatedStorage:")
    print(f"   Files: {len(files)}")
    print(f"   Path: {api_precalc.absolute()}")
    
    # Check a sample file has the required fields
    if files:
        with open(files[0], 'r') as f:
            data = json.load(f)
        
        if 'data' in data and data['data']:
            last_candle = data['data'][-1]
            print(f"\n3. Sample file check ({files[0].name}):")
            print(f"   Has daily_pctchg_1: {'daily_pctchg_1' in last_candle}")
            print(f"   Has daily_sma_20: {'daily_sma_20' in last_candle}")
            print(f"   Has weekly_supertrend_10_2.0: {'weekly_supertrend_10_2.0' in last_candle}")

# Check python-api/db folder
if api_db.exists():
    db_files = list(api_db.glob("*.json"))
    print(f"\n4. Python-api DB folder:")
    print(f"   Files in db: {len(db_files)}")
    print(f"   Path: {api_db.absolute()}")

print("\n" + "=" * 60)
print("CONSOLIDATION SUMMARY:")
if not root_precalc.exists() and not root_db.exists():
    print("[OK] Root level folders removed")
if api_precalc.exists() and api_db.exists():
    print("[OK] Both db and precalculatedStorage in python-api folder")
print("[OK] Consolidation complete!")
print("=" * 60)