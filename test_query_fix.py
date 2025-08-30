import asyncio
import aiohttp
import json

async def test_query():
    """Test the query endpoint to see if it triggers migration"""
    url = "http://localhost:8001/api/query/latest"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json'
    }
    data = {"query": "daily_supertrend_10_3 > 100"}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=data, headers=headers) as response:
                result = await response.json()
                print(f"Response status: {response.status}")
                print(f"Response: {json.dumps(result, indent=2)}")
                
                if response.status == 200:
                    print("\n✅ Query executed successfully!")
                else:
                    print(f"\n❌ Query failed with status {response.status}")
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_query())
