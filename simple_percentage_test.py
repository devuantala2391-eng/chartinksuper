"""
Simple test for percentage calculation API
"""

import requests
import json

# Test the API with a query that requires daily percentage  
# Query should be a string in Chartink format
# Try different field names for daily percentage change
queries_to_test = [
    "( {daily pctchg} > -50 )",
    "( {daily_pctchg} > -50 )",
    "( {pctchg} > -50 )",
    "( {close} > 0 )"  # Simple test to make sure query parsing works
]

query_data = {
    "query": queries_to_test[3],  # Start with simple query
    "stocks": ["20MICRONS"]
}

try:
    print("Testing percentage calculation API...")
    response = requests.post(
        "http://127.0.0.1:8001/api/query/latest",
        json=query_data,
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("SUCCESS: Query worked!")
        print(f"Matches: {len(result.get('matches', []))}")
        if result.get('matches'):
            print(f"Sample: {result['matches'][0]}")
    else:
        print("FAILED:")
        print(response.text)

except Exception as e:
    print(f"Error: {e}")
    