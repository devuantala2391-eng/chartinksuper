#!/usr/bin/env python3
"""Test script to verify auto-calculation fixes"""

import requests
import json
import time

def test_auto_calculation():
    """Test the auto-calculation feature with a query that has missing indicators"""
    
    # Query that requires indicators not yet calculated
    test_query = {
        "query": "daily_volume > 50000 and daily_pctchg_1 < 9 and weekly_supertrend_10_2 > weekly_close"
    }
    
    print("=" * 60)
    print("TESTING AUTO-CALCULATION FEATURE")
    print("=" * 60)
    
    print("\n1. Sending query with missing indicators...")
    print(f"Query: {test_query['query']}")
    
    try:
        # Send query to latest endpoint
        response = requests.post(
            "http://localhost:8001/api/query/latest",
            json=test_query,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\n2. Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS! Query executed successfully")
            print(f"Matches found: {result.get('totalMatches', 0)}")
            if result.get('results'):
                print(f"Sample results: {result['results'][:3]}")
        else:
            result = response.json()
            print("RESPONSE:", json.dumps(result, indent=2))
            
            if "missing_fields" in result.get("detail", {}):
                missing = result["detail"]["missing_fields"]
                print(f"\nMissing fields detected: {missing}")
                print("Auto-calculation should have triggered...")
                
                # Wait a bit and check if indicators are being calculated
                print("\n3. Checking precalculation status...")
                time.sleep(2)
                
                status_response = requests.get(
                    "http://localhost:8001/api/get-precalculated-indicators",
                    headers={"ngrok-skip-browser-warning": "69420"}
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"Status: {status_data.get('status')}")
                    print(f"Indicators: {len(status_data.get('indicators', []))}")
                    
                    # Check if the missing indicators were added
                    indicators = status_data.get('indicators', [])
                    for ind in indicators:
                        if ind.get('name') == 'pctchg' and ind.get('timeframe') == 'daily':
                            print("OK daily_pctchg_1 was added to config")
                        if ind.get('name') == 'supertrend' and ind.get('timeframe') == 'weekly':
                            print(f"OK weekly_supertrend was added: {ind}")
                
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out - server might be hanging")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_auto_calculation()