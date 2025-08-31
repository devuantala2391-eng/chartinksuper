import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_database_data():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== DATABASE STATUS ===")
    
    # Check tables
    tables = await conn.fetch("""
        SELECT table_name, 
               (SELECT COUNT(*) FROM information_schema.tables t2 WHERE t2.table_name = t1.table_name) as count
        FROM information_schema.tables t1
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    print("\nTables in database:")
    for table in tables:
        table_name = table['table_name']
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
        print(f"  {table_name}: {count} rows")
    
    # Check daily_candles specifically
    daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
    print(f"\nDaily candles total: {daily_count}")
    
    if daily_count > 0:
        # Check for 20MICRONS specifically
        microns_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = '20MICRONS'")
        print(f"20MICRONS candles: {microns_count}")
        
        # Check if any indicators exist
        indicators_count = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM daily_candles 
            WHERE indicators IS NOT NULL AND indicators != '{}'
        """)
        print(f"Rows with indicators: {indicators_count}")
        
        # Sample a row with indicators
        sample = await conn.fetchrow("""
            SELECT symbol, indicators 
            FROM daily_candles 
            WHERE indicators IS NOT NULL AND indicators != '{}'
            LIMIT 1
        """)
        
        if sample:
            print(f"\nSample indicators from {sample['symbol']}:")
            import json
            indicators = sample['indicators']
            if isinstance(indicators, str):
                indicators = json.loads(indicators)
            for key in list(indicators.keys())[:5]:  # Show first 5 indicators
                print(f"  {key}: {indicators[key]}")
    
    await conn.close()

asyncio.run(check_database_data())
