import requests
import json

# Test the API with monthly percentage query
query_data = {
    "query": "( {monthly pctchg} > -5 )",
    "stocks": ["20MICRONS"]
}

try:
    print("Testing monthly percentage calculation API...")
    response = requests.post(
        "http://127.0.0.1:8001/api/query/latest",
        json=query_data,
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("SUCCESS: Monthly percentage query worked!")
        print(f"Matches: {len(result.get('matches', []))}")
        if result.get('matches'):
            # Show first few matches
            for i, match in enumerate(result['matches'][:5]):
                monthly_pct = match.get('monthly_pctchg', 'N/A')
                print(f"  Match {i+1}: {match.get('symbol')} on {match.get('date')}: monthly_pctchg={monthly_pct}%")
    else:
        print("FAILED:")
        print(response.text)

except Exception as e:
    print(f"Error: {e}")