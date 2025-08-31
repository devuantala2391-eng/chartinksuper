"""
Test API with various queries to ensure prefixed indicators work correctly
"""
import requests
import json

def test_query(description, query):
    """Test a query against the API"""
    print(f"\n{description}")
    print(f"Query: {query}")
    
    url = "http://localhost:8001/query/latest"
    payload = {"query": query}
    
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if 'results' in data:
                count = len(data['results'])
                print(f"  [OK] Success: {count} results found")
                if count > 0:
                    # Show first result as sample
                    first = data['results'][0]
                    print(f"  Sample: {first['symbol']} - Close: {first.get('close', 'N/A')}")
                    # Check if indicators are present
                    if 'indicators' in first and first['indicators']:
                        indicators = json.loads(first['indicators']) if isinstance(first['indicators'], str) else first['indicators']
                        print(f"  Indicators present: {', '.join(list(indicators.keys())[:5])}")
            elif 'error' in data:
                print(f"  [X] Error: {data['error']}")
            else:
                print(f"  Response: {data}")
        else:
            print(f"  [X] HTTP Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"  [X] Exception: {e}")

def main():
    print("="*60)
    print("TESTING API WITH PREFIXED INDICATORS")
    print("="*60)
    
    # Test 1: Daily percentage change
    test_query(
        "Test 1: Daily percentage change > 2%",
        "daily_pctchg > 2"
    )
    
    # Test 2: Weekly percentage change
    test_query(
        "Test 2: Weekly percentage change < -5%",
        "weekly_pctchg < -5"
    )
    
    # Test 3: Monthly percentage change
    test_query(
        "Test 3: Monthly percentage change > 10%",
        "monthly_pctchg > 10"
    )
    
    # Test 4: Daily SuperTrend
    test_query(
        "Test 4: Daily SuperTrend direction = 1 (bullish)",
        "daily_supertrend_10_3_direction = 1"
    )
    
    # Test 5: Weekly SuperTrend
    test_query(
        "Test 5: Weekly SuperTrend < 200",
        "weekly_supertrend_10_3 < 200"
    )
    
    # Test 6: Monthly SuperTrend
    test_query(
        "Test 6: Monthly SuperTrend direction = 0 (bearish)",
        "monthly_supertrend_10_3_direction = 0"
    )
    
    # Test 7: Complex query with multiple conditions
    test_query(
        "Test 7: Complex - Daily up, Weekly up, price > daily SuperTrend",
        "daily_pctchg > 0 and weekly_pctchg > 0 and close > daily_supertrend_10_3"
    )
    
    # Test 8: Volume-based query
    test_query(
        "Test 8: High volume stocks",
        "volume > 1000000"
    )
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == '__main__':
    main()