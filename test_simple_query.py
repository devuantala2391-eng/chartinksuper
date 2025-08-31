"""
Simple test to verify API is working with prefixed indicators
"""
import requests
import json

def test_simple():
    url = "http://localhost:8001/query/latest"
    
    # Test 1: Simple daily percentage change query
    print("\nTest 1: Daily percentage change > 0")
    query = "daily_pctchg > 0"
    
    try:
        response = requests.post(url, json={"query": query}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'results' in data:
                print(f"Success! Found {len(data['results'])} results")
                if data['results']:
                    first = data['results'][0]
                    print(f"Sample: {first['symbol']}")
                    # Check indicators
                    if 'indicators' in first:
                        indicators = json.loads(first['indicators']) if isinstance(first['indicators'], str) else first['indicators']
                        if 'daily_pctchg' in indicators:
                            print(f"  daily_pctchg: {indicators['daily_pctchg']}")
                        if 'weekly_pctchg' in indicators:
                            print(f"  weekly_pctchg: {indicators['weekly_pctchg']}")
                        if 'daily_supertrend_10_3' in indicators:
                            print(f"  daily_supertrend_10_3: {indicators['daily_supertrend_10_3']}")
                        if 'weekly_supertrend_10_3' in indicators:
                            print(f"  weekly_supertrend_10_3: {indicators['weekly_supertrend_10_3']}")
            elif 'error' in data:
                print(f"Error: {data['error']}")
        else:
            print(f"HTTP Error {response.status_code}")
            
    except requests.Timeout:
        print("Request timed out after 10 seconds")
    except Exception as e:
        print(f"Exception: {e}")
    
    # Test 2: Check database directly
    print("\n\nTest 2: Checking database directly...")
    import asyncio
    import asyncpg
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def check_db():
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        try:
            # Check what indicators are stored
            row = await conn.fetchrow("""
                SELECT candle_key_id, indicators
                FROM daily_candles
                WHERE symbol = '20MICRONS'
                AND indicators IS NOT NULL
                ORDER BY candle_sequence_number DESC
                LIMIT 1
            """)
            
            if row:
                print(f"Latest candle: {row['candle_key_id']}")
                indicators = json.loads(row['indicators']) if isinstance(row['indicators'], str) else row['indicators']
                print("Indicators present:")
                for key in sorted(indicators.keys()):
                    print(f"  - {key}: {indicators[key]}")
                    
        finally:
            await conn.close()
    
    asyncio.run(check_db())

if __name__ == '__main__':
    test_simple()