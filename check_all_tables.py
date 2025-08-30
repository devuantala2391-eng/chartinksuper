import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_all_tables():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    # Get ALL tables
    tables = await conn.fetch("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    print("ALL TABLES IN DATABASE:")
    for table in tables:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
        print(f"  {table['table_name']}: {count} rows")
    
    # Check schema of daily_candles
    print("\nDAILY_CANDLES SCHEMA:")
    columns = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'daily_candles'
        ORDER BY ordinal_position
    """)
    for col in columns:
        print(f"  {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    
    await conn.close()

asyncio.run(check_all_tables())
