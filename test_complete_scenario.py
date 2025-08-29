"""
Test complete scenario: hard refresh -> first API call (should calculate) -> second API call (should not recalculate)
"""

import requests
import json
import time

def test_api_call(test_name, query, expected_behavior):
    """Make an API call and measure timing"""
    print(f"\n{test_name}:")
    print(f"  Query: {query}")
    
    start_time = time.time()
    try:
        response = requests.post(
            "http://127.0.0.1:8001/api/query/latest",
            json={"query": query, "stocks": ["20MICRONS"]},
            timeout=30
        )
        duration = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            matches = len(result.get('matches', []))
            print(f"  SUCCESS: {matches} matches in {duration:.3f}s")
            print(f"  Expected: {expected_behavior}")
            return True, duration, matches
        else:
            print(f"  FAILED: Status {response.status_code}")
            print(f"  Response: {response.text}")
            return False, duration, 0
            
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        print(f"  TIMEOUT after {duration:.1f}s")
        return False, duration, 0
    except Exception as e:
        duration = time.time() - start_time
        print(f"  ERROR: {e}")
        return False, duration, 0

def main():
    print("=== COMPLETE SCENARIO TEST ===")
    print("Testing: Hard refresh -> First API call -> Second API call")
    
    # Test different percentage indicators
    test_cases = [
        ("( {daily pctchg} > -10 )", "Daily percentage - should calculate on first call, skip on second"),
        ("( {weekly pctchg} > -10 )", "Weekly percentage - should calculate on first call, skip on second"),
        ("( {monthly pctchg} > -10 )", "Monthly percentage - should calculate on first call, skip on second")
    ]
    
    print("\nNOTE: Make sure to do hard refresh before running this test!")
    print("This test assumes indicators have been cleared by hard refresh.\n")
    
    for query, description in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {description}")
        
        # First call - should calculate indicators
        success1, time1, matches1 = test_api_call("First API Call", query, "Should calculate indicators (slower)")
        
        if success1:
            # Second call - should NOT recalculate indicators 
            success2, time2, matches2 = test_api_call("Second API Call", query, "Should use existing indicators (faster)")
            
            if success2:
                # Analyze timing
                if time2 < time1:
                    print(f"  ✅ GOOD: Second call faster ({time2:.3f}s vs {time1:.3f}s)")
                    print(f"  ✅ Speedup: {time1/time2:.1f}x faster on second call")
                else:
                    print(f"  ⚠️  Second call not faster ({time2:.3f}s vs {time1:.3f}s)")
                
                # Verify same results
                if matches1 == matches2:
                    print(f"  ✅ GOOD: Consistent results ({matches1} matches both times)")
                else:
                    print(f"  ❌ PROBLEM: Different results ({matches1} vs {matches2} matches)")
            else:
                print("  ❌ Second call failed")
        else:
            print("  ❌ First call failed - skipping second call")
    
    print(f"\n{'='*60}")
    print("SUMMARY:")
    print("- First calls should be slower (calculating indicators)")
    print("- Second calls should be faster (using existing indicators)")
    print("- Results should be consistent between calls")

if __name__ == "__main__":
    main()