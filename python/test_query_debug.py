import sys
import traceback
import asyncio
from main import app, QueryRequest
from fastapi.testclient import TestClient

client = TestClient(app)

try:
    print("Testing query endpoint with TestClient...")
    response = client.post('/query', json={'query': 'daily_rsi_14 > 150'})
    print('Status code:', response.status_code)
    if response.status_code != 200:
        print('Response text:', response.text)
        print('Response headers:', dict(response.headers))
    else:
        result = response.json()
        print('Response keys:', list(result.keys()))
        print('Total matches:', result.get('totalMatches', 0))
        print('Success:', result.get('success', False))
except Exception as e:
    print('Test client error:')
    traceback.print_exc()