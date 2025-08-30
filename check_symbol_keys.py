import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_symbol_keys():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== SYMBOL_LATEST_KEYS TABLE DATA ===")
    
    # Check symbol_latest_keys schema
    columns = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'symbol_latest_keys'
        ORDER BY ordinal_position
    """)
    
    print("SCHEMA:")
    for col in columns:
        print(f"  {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    
    # Check data
    rows = await conn.fetch("SELECT * FROM symbol_latest_keys ORDER BY symbol")
    print(f"\nDATA ({len(rows)} rows):")
    for row in rows:
        print(f"  Symbol: {row['symbol']}")
        print(f"    Daily Key: {row.get('latest_daily_key', 'N/A')}")
        print(f"    Weekly Key: {row.get('latest_weekly_key', 'N/A')}")  
        print(f"    Monthly Key: {row.get('latest_monthly_key', 'N/A')}")
        print(f"    Daily Count: {row.get('total_daily_candles', 'N/A')}")
        print()
    
    # Also check actual weekly and monthly candles counts
    print("=== ACTUAL CANDLE COUNTS ===")
    daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
    weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")  
    monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
    
    print(f"Daily candles: {daily_count}")
    print(f"Weekly candles: {weekly_count}")
    print(f"Monthly candles: {monthly_count}")
    
    # Check max sequence numbers
    if weekly_count > 0:
        max_weekly = await conn.fetchrow("SELECT symbol, MAX(week_sequence_number) as max_seq FROM weekly_candles GROUP BY symbol ORDER BY symbol")
        print(f"Max weekly sequence: {max_weekly}")
        
    if monthly_count > 0:
        max_monthly = await conn.fetchrow("SELECT symbol, MAX(month_sequence_number) as max_seq FROM monthly_candles GROUP BY symbol ORDER BY symbol")
        print(f"Max monthly sequence: {max_monthly}")
    
    await conn.close()

asyncio.run(check_symbol_keys())
