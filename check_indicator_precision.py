import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check_indicator_precision():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== CHECKING INDICATOR PRECISION ===")
    
    # Get a sample of indicators from database
    rows = await conn.fetch("""
        SELECT symbol, indicators 
        FROM daily_candles 
        WHERE indicators IS NOT NULL AND indicators != '{}' 
        LIMIT 3
    """)
    
    for row in rows:
        symbol = row['symbol']
        indicators = row['indicators']
        
        if isinstance(indicators, str):
            indicators = json.loads(indicators)
        
        print(f"\nSymbol: {symbol}")
        print("Indicators:")
        
        for key, value in indicators.items():
            print(f"  {key}: {value} (type: {type(value)})")
            if isinstance(value, (int, float)):
                decimal_places = len(str(value).split('.')[-1]) if '.' in str(value) else 0
                print(f"    Decimal places: {decimal_places}")
    
    # Check what supertrend indicators exist
    print("\n=== SUPERTREND INDICATORS IN DATABASE ===")
    
    # Get all unique indicator keys that contain supertrend
    try:
        indicator_keys = await conn.fetch("""
            SELECT DISTINCT jsonb_object_keys(indicators) as key
            FROM daily_candles 
            WHERE indicators IS NOT NULL 
            AND indicators::text LIKE '%supertrend%'
        """)
        
        supertrend_keys = []
        for row in indicator_keys:
            key = row['key']
            if 'supertrend' in key.lower():
                supertrend_keys.append(key)
                print(f"  Found: {key}")
        
        if not supertrend_keys:
            print("  No supertrend indicators found in database")
            
    except Exception as e:
        print(f"  Error checking supertrend indicators: {e}")
    
    await conn.close()

asyncio.run(check_indicator_precision())
