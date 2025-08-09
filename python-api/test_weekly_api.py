import requests
import json
import time
from pathlib import Path

def test_weekly_supertrend_api():
    """Test that weekly_supertrend_30_1.56 is auto-calculated."""
    
    base_url = "http://localhost:8001"
    test_query = "daily_pctchg_1 < 9 and daily_pctchg_1 > 0 and weekly_supertrend_30_1.56 > 20"
    
    print("=" * 60)
    print("TESTING WEEKLY SUPERTREND AUTO-CALCULATION")
    print("=" * 60)
    print(f"\nQuery: {test_query}")
    print("-" * 60)
    
    # Check initial state
    precalc_file = Path("precalculatedIndicators.json")
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            indicators = data.get('indicators', [])
            
            # Check if weekly_supertrend_30_1.56 exists
            exists_before = any(
                ind.get('timeframe') == 'weekly' and
                ind.get('name') == 'supertrend' and
                ind.get('params', {}).get('period') == 30 and
                ind.get('params', {}).get('multiplier') == 1.56
                for ind in indicators
            )
            
            print(f"weekly_supertrend_30_1.56 exists before: {exists_before}")
    
    print("\nMaking API request...")
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{base_url}/api/query/latest",
            json={"query": test_query},
            timeout=120
        )
        
        elapsed = time.time() - start_time
        print(f"Response received in {elapsed:.2f} seconds")
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            matches = len(result.get('result', []))
            print(f"[SUCCESS] Query executed! Found {matches} matches")
            
            # Check if indicator was added
            with open(precalc_file, 'r') as f:
                data = json.load(f)
                indicators = data.get('indicators', [])
                
                exists_after = any(
                    ind.get('timeframe') == 'weekly' and
                    ind.get('name') == 'supertrend' and
                    ind.get('params', {}).get('period') == 30 and
                    ind.get('params', {}).get('multiplier') == 1.56
                    for ind in indicators
                )
                
                print(f"\nweekly_supertrend_30_1.56 exists after: {exists_after}")
                
                if exists_after and not exists_before:
                    print("[SUCCESS] weekly_supertrend_30_1.56 was auto-added!")
                elif exists_after:
                    print("[INFO] weekly_supertrend_30_1.56 already existed")
                else:
                    print("[ERROR] weekly_supertrend_30_1.56 was NOT added")
            
            # Check a sample data file
            sample_file = Path("precalculatedStorage/3PLAND_piped.json")
            if sample_file.exists():
                with open(sample_file, 'r') as f:
                    stock_data = json.load(f)
                    if stock_data.get("data"):
                        last_candle = stock_data["data"][-1]
                        has_field = "weekly_supertrend_30_1.56" in last_candle
                        print(f"\nData file has weekly_supertrend_30_1.56: {has_field}")
                        if has_field:
                            value = last_candle.get("weekly_supertrend_30_1.56")
                            print(f"Value: {value}")
        else:
            print(f"[ERROR] Status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    test_weekly_supertrend_api()