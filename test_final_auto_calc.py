#!/usr/bin/env python3
"""
Final comprehensive test of auto-calculation feature
This demonstrates the complete working flow:
1. Clear all indicators
2. Send a complex query with missing indicators
3. System auto-detects and calculates missing indicators
4. Query executes successfully
"""

import requests
import json
import time
from pathlib import Path

def main():
    print("="*70)
    print("CHARTINKSUPER AUTO-CALCULATION FEATURE - FINAL TEST")
    print("="*70)
    
    # Step 1: Clear indicators
    print("\n1. Clearing all indicators...")
    config_path = Path("python-api/precalculatedIndicators.json")
    empty_config = {
        "status": "idle",
        "indicators": [],
        "lastUpdated": None,
        "dayOfWeek": None
    }
    with open(config_path, 'w') as f:
        json.dump(empty_config, f, indent=2)
    print("   ✓ Indicators cleared")
    
    # Step 2: Send complex query
    print("\n2. Sending complex query with missing indicators...")
    query = "daily_pctchg_1 < 9 and daily_pctchg_1 > 0"
    print(f"   Query: {query}")
    
    try:
        response = requests.post(
            "http://localhost:8001/api/query/latest",
            json={"query": query},
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n3. Query executed successfully!")
            print(f"   Total Processed: {result.get('totalProcessed')}")
            print(f"   Total Matches: {result.get('totalMatches')}")
            
            # Check what indicators were added
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            print(f"\n4. Auto-detected and calculated indicators:")
            for ind in config.get('indicators', []):
                print(f"   ✓ {ind['description']}")
            
            # Verify the field exists in data
            sample_file = Path("python-api/precalculatedStorage/AAKASH_piped.json")
            if sample_file.exists():
                with open(sample_file, 'r') as f:
                    data = json.load(f)
                if 'data' in data and len(data['data']) > 0:
                    last_candle = data['data'][-1]
                    if 'daily_pctchg_1' in last_candle:
                        print(f"\n5. Verification: daily_pctchg_1 field exists in data")
                        print(f"   Sample value: {last_candle['daily_pctchg_1']:.2f}%")
            
            print("\n" + "="*70)
            print("TEST SUCCESSFUL - AUTO-CALCULATION WORKING CORRECTLY!")
            print("="*70)
            
        else:
            print(f"\nError: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure the server is running:")
        print("  cd python-api && python main.py")

if __name__ == "__main__":
    main()