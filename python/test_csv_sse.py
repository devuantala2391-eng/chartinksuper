import asyncio
import aiohttp
import json

async def test_csv_sse():
    """Test the CSV upload SSE endpoint."""
    print("Testing CSV Upload SSE...")
    
    # Connect to SSE endpoint
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:8001/csv-upload-progress-stream') as response:
            print(f"Connected to SSE endpoint: {response.status}")
            
            # Read first few messages
            count = 0
            async for line in response.content:
                if count > 5:  # Just read first 5 messages
                    break
                    
                decoded = line.decode('utf-8').strip()
                if decoded.startswith('data:'):
                    data = decoded[5:].strip()
                    try:
                        parsed = json.loads(data)
                        print(f"Received: {parsed}")
                        count += 1
                    except json.JSONDecodeError:
                        pass
                elif decoded.startswith(':'):
                    print(f"Heartbeat: {decoded}")

if __name__ == "__main__":
    asyncio.run(test_csv_sse())