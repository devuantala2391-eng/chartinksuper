import requests
import json

# Test both queries
queries = [
    "weekly_volume > 1 week ago weekly_volume",
    "weekly_volume > 1 week ago weekly_volume * 1", 
    "weekly_volume > 1 week ago weekly_volume * 2"
]

for query in queries:
    response = requests.post(
        'http://localhost:8001/query/latest',
        headers={'Content-Type': 'application/json'},
        json={'query': query},
        timeout=10
    )
    
    data = response.json()
    print(f"Query: {query}")
    print(f"  Total matches: {data.get('totalMatches', 0)}")
    print(f"  Success: {data.get('success', False)}")
    if not data.get('success', False):
        print(f"  Error: {data.get('error', 'Unknown error')}")
    print()