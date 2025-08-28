"""
Test the percentage calculation API fix

This tests that daily percentage queries work properly
after fixing the PostgreSQL function conflicts.
"""

import requests
import json

def test_percentage_api():
    """Test the query/latest API with percentage calculations"""
    
    print("=== TESTING PERCENTAGE CALCULATION API ===")
    
    # Test 1: Check if server is running
    try:
        response = requests.get("http://127.0.0.1:8001/health", timeout=5)
        if response.status_code == 200:
            print("SUCCESS: API server is running")
        else:
            print(f"WARNING: Health check returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Cannot connect to API server: {e}")
        return False
    
    # Test 2: Test query with daily percentage
    print("\n=== TESTING DAILY PERCENTAGE QUERY ===")
    
    # Create a query that requires daily percentage calculation
    test_query = {
        "conditions": [
            {
                "left": {
                    "type": "field",
                    "field": "daily pctchg"
                },
                "operator": ">",
                "right": {
                    "type": "value", 
                    "value": 1.0
                }
            }
        ],
        "logic": "AND"
    }
    
    try:
        print("Sending query with daily percentage condition...")
        response = requests.post(
            "http://127.0.0.1:8001/api/query/latest",
            json={
                "query": test_query,
                "symbols": ["20MICRONS"]  # Test with our known symbol
            },
            timeout=30
        )
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS: Query completed without errors")
            print(f"Matches found: {len(result.get('matches', []))}")
            print(f"Errors: {len(result.get('errors', []))}")
            
            # Print first match if available
            if result.get('matches'):
                print("Sample match:")
                match = result['matches'][0]
                print(f"  Symbol: {match.get('symbol')}")
                print(f"  Date: {match.get('date')}")
                print(f"  Daily pctchg: {match.get('daily_pctchg', 'N/A')}")
            
            return True
            
        elif response.status_code == 400:
            print("ERROR: Query failed with 400 error")
            error_detail = response.json()
            print(f"Error details: {error_detail}")
            return False
            
        else:
            print(f"ERROR: Unexpected response status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse response: {e}")
        print(f"Raw response: {response.text}")
        return False
    
def test_simple_query():
    """Test a simple query first to make sure basic functionality works"""
    
    print("\n=== TESTING SIMPLE QUERY (NO PERCENTAGE) ===")
    
    # Simple query without percentage
    simple_query = {
        "conditions": [
            {
                "left": {
                    "type": "field",
                    "field": "close"
                },
                "operator": ">",
                "right": {
                    "type": "value", 
                    "value": 0
                }
            }
        ],
        "logic": "AND"
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8001/api/query/latest",
            json={
                "query": simple_query,
                "symbols": ["20MICRONS"]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS: Simple query works")
            print(f"Matches: {len(result.get('matches', []))}")
            return True
        else:
            print(f"ERROR: Simple query failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: Simple query failed: {e}")
        return False

if __name__ == "__main__":
    # First test basic functionality
    simple_works = test_simple_query()
    
    if simple_works:
        print("\nBasic functionality confirmed. Testing percentage...")
        percentage_works = test_percentage_api()
        
        if percentage_works:
            print("\n=== ALL TESTS PASSED ===")
            print("✅ Percentage calculation API is working correctly!")
            print("✅ PostgreSQL function conflicts have been resolved!")
        else:
            print("\n=== PERCENTAGE TEST FAILED ===")
            print("❌ Percentage calculation still has issues")
    else:
        print("\n=== BASIC FUNCTIONALITY FAILED ===")
        print("❌ API server has fundamental issues")