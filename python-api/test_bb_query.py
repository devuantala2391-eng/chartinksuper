import requests
import json

def test_bb_query():
    """Test Bollinger Bands query with decimal parameters."""
    
    base_url = "http://localhost:8001"
    test_query = "daily_bb_upper_10_1.22 > 30"
    
    print(f"Testing query: {test_query}")
    print("-" * 60)
    
    response = requests.post(
        f"{base_url}/api/query/latest",
        json={"query": test_query},
        timeout=60
    )
    
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        matches = len(result.get('result', []))
        print(f"[SUCCESS] Found {matches} matches")
        
        # Show first few results
        if result.get('result'):
            print("\nFirst 3 results:")
            for i, item in enumerate(result['result'][:3]):
                print(f"  {i+1}. {item.get('symbol', 'N/A')}")
    else:
        print(f"[ERROR] {response.status_code}")
        print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    test_bb_query()