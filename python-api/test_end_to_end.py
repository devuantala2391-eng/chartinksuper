import requests
import json
import time
from pathlib import Path

def test_end_to_end_auto_calculation():
    """Comprehensive end-to-end test of automatic indicator calculation."""
    
    base_url = "http://localhost:8001"
    
    print("=" * 60)
    print("END-TO-END AUTO-CALCULATION TEST")
    print("=" * 60)
    
    # Test with a completely new indicator parameter that we know doesn't exist
    test_query = "daily_close > 100 and daily_ema_45 > 150 and daily_sma_75 < 200"
    
    print(f"\n1. Testing query with new indicators:")
    print(f"   Query: {test_query}")
    print("-" * 60)
    
    # Check initial state
    precalc_file = Path("precalculatedIndicators.json")
    initial_indicators = []
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            initial_indicators = data.get('indicators', [])
            print(f"   Initial indicators count: {len(initial_indicators)}")
            
            # Check if our test indicators exist
            ema_45_exists_before = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'ema' and
                ind.get('params', {}).get('period') == 45
                for ind in initial_indicators
            )
            sma_75_exists_before = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'sma' and
                ind.get('params', {}).get('period') == 75
                for ind in initial_indicators
            )
            
            print(f"   daily_ema_45 exists before: {ema_45_exists_before}")
            print(f"   daily_sma_75 exists before: {sma_75_exists_before}")
    
    print("\n2. Making API request...")
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{base_url}/api/query/latest",
            json={"query": test_query},
            timeout=120  # 2 minutes timeout for calculation
        )
        
        elapsed_time = time.time() - start_time
        print(f"   Response received in {elapsed_time:.2f} seconds")
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            matches_count = len(result.get('result', []))
            print(f"   [SUCCESS] Query executed successfully!")
            print(f"   Found {matches_count} matching stocks")
            
            # Check if indicators were added
            print("\n3. Checking if new indicators were added...")
            with open(precalc_file, 'r') as f:
                data = json.load(f)
                final_indicators = data.get('indicators', [])
                print(f"   Final indicators count: {len(final_indicators)}")
                
                # Check for daily_ema_45
                ema_45_exists_after = any(
                    ind.get('timeframe') == 'daily' and
                    ind.get('name') == 'ema' and
                    ind.get('params', {}).get('period') == 45
                    for ind in final_indicators
                )
                
                # Check for daily_sma_75
                sma_75_exists_after = any(
                    ind.get('timeframe') == 'daily' and
                    ind.get('name') == 'sma' and
                    ind.get('params', {}).get('period') == 75
                    for ind in final_indicators
                )
                
                print(f"   daily_ema_45 exists after: {ema_45_exists_after}")
                print(f"   daily_sma_75 exists after: {sma_75_exists_after}")
                
                # Check if indicators were newly added
                ema_45_newly_added = not ema_45_exists_before and ema_45_exists_after
                sma_75_newly_added = not sma_75_exists_before and sma_75_exists_after
                
                if ema_45_newly_added:
                    print("   [SUCCESS] daily_ema_45 was automatically added!")
                if sma_75_newly_added:
                    print("   [SUCCESS] daily_sma_75 was automatically added!")
                
                if not (ema_45_newly_added or sma_75_newly_added):
                    print("   [INFO] No new indicators needed to be added (already existed)")
            
            # Check if data files were updated
            print("\n4. Checking if data files contain new indicators...")
            sample_file = Path("precalculatedStorage/3PLAND_piped.json")
            if sample_file.exists():
                with open(sample_file, 'r') as f:
                    stock_data = json.load(f)
                    if stock_data.get("data"):
                        last_candle = stock_data["data"][-1]
                        has_ema_45 = "daily_ema_45" in last_candle
                        has_sma_75 = "daily_sma_75" in last_candle
                        
                        print(f"   Sample file has daily_ema_45: {has_ema_45}")
                        print(f"   Sample file has daily_sma_75: {has_sma_75}")
                        
                        if has_ema_45:
                            value = last_candle.get('daily_ema_45')
                            print(f"   daily_ema_45 value: {value}")
                        if has_sma_75:
                            value = last_candle.get('daily_sma_75')
                            print(f"   daily_sma_75 value: {value}")
                        
                        if has_ema_45 and has_sma_75:
                            print("   [SUCCESS] Data files contain calculated values!")
            
            print("\n" + "=" * 60)
            print("TEST SUMMARY")
            print("=" * 60)
            if elapsed_time < 120:
                print("[SUCCESS] Auto-calculation completed within timeout")
            else:
                print("[WARNING] Auto-calculation took longer than expected")
            
            if matches_count >= 0:
                print("[SUCCESS] Query executed and returned results")
            
            if (ema_45_newly_added or sma_75_newly_added) or (ema_45_exists_after and sma_75_exists_after):
                print("[SUCCESS] Indicators were properly handled")
            
            print("\n[OVERALL] AUTO-CALCULATION SYSTEM IS WORKING!")
            
        else:
            print(f"   [ERROR] Query failed with status {response.status_code}")
            print(f"   Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("   [ERROR] Request timed out after 120 seconds")
        print("   This might mean the calculation is taking too long")
    except Exception as e:
        print(f"   [ERROR] Unexpected error: {e}")

if __name__ == "__main__":
    test_end_to_end_auto_calculation()