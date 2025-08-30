import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check_any_indicators():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== CHECKING FOR ANY INDICATORS ===")
    
    # Check if indicators column has any non-empty values
    total_rows = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
    non_null_indicators = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE indicators IS NOT NULL")
    non_empty_indicators = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE indicators IS NOT NULL AND indicators != '{}'")
    
    print(f"Total daily_candles: {total_rows}")
    print(f"Rows with non-null indicators: {non_null_indicators}")
    print(f"Rows with non-empty indicators: {non_empty_indicators}")
    
    # Get a sample of any existing indicators
    if non_empty_indicators > 0:
        sample = await conn.fetch("""
            SELECT symbol, indicators 
            FROM daily_candles 
            WHERE indicators IS NOT NULL AND indicators != '{}' 
            LIMIT 2
        """)
        
        for row in sample:
            indicators = row['indicators']
            if isinstance(indicators, str):
                indicators = json.loads(indicators)
            
            print(f"\nSample indicators for {row['symbol']}:")
            for key, value in indicators.items():
                print(f"  {key}: {value}")
    
    await conn.close()

asyncio.run(check_any_indicators())
