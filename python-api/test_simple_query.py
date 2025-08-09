import requests
import json

def test_simple_query():
    """Test a simple query without new indicators to establish baseline."""
    
    base_url = "http://localhost:8001"
    
    # Use a simple query with existing indicators
    test_query = "daily_close > 100"
    
    print(f"Testing simple query: {test_query}")
    print("-" * 60)
    
    try:
        response = requests.post(
            f"{base_url}/api/query/latest",
            json={"query": test_query},
            timeout=30
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Success! Found {len(result.get('result', []))} stocks")
            if result.get('result'):
                print(f"First result: {result['result'][0].get('symbol', 'N/A')}")
        else:
            print(f"Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("Request timed out after 30 seconds")
    except Exception as e:
        print(f"Error: {e}")

def test_new_indicator_query():
    """Test a query with a new indicator parameter."""
    
    base_url = "http://localhost:8001"
    
    # Use a query with a new indicator parameter
    test_query = "daily_close > 100 and daily_rsi_30 > 40"
    
    print(f"\nTesting query with new indicator: {test_query}")
    print("-" * 60)
    
    try:
        response = requests.post(
            f"{base_url}/api/query/latest",
            json={"query": test_query},
            timeout=60
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Success! Found {len(result.get('result', []))} stocks")
            
            # Check if the indicator was added
            with open("precalculatedIndicators.json", 'r') as f:
                data = json.load(f)
                indicators = data.get('indicators', [])
                
                # Check for daily_rsi_30
                rsi_30_exists = any(
                    ind.get('timeframe') == 'daily' and
                    ind.get('name') == 'rsi' and
                    ind.get('params', {}).get('period') == 30
                    for ind in indicators
                )
                
                if rsi_30_exists:
                    print("[SUCCESS] New indicator daily_rsi_30 was added successfully!")
                else:
                    print("[ERROR] New indicator daily_rsi_30 was NOT added")
                    
        else:
            print(f"Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("Request timed out after 60 seconds")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Query API")
    print("=" * 60)
    
    # First test simple query
    test_simple_query()
    
    # Then test with new indicator
    test_new_indicator_query()