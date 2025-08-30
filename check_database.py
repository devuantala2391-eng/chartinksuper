"""
Quick database check to see current state
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_database():
    """Check database state"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("SUCCESS: Database connection successful")
        print("=" * 50)
        
        # Check tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('daily_candles', 'weekly_candles', 'monthly_candles')
            ORDER BY table_name
        """)
        
        print("AVAILABLE TABLES:")
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
            print(f"  {table['table_name']}: {count} rows")
        
        # Check stored procedures
        procedures = await conn.fetch("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_type = 'FUNCTION'
            AND routine_name LIKE '%weekly%'
            ORDER BY routine_name
        """)
        
        print(f"\nWEEKLY PROCEDURES:")
        for proc in procedures:
            print(f"  {proc['routine_name']}")
        
        # If we have daily candles, check some details
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        if daily_count > 0:
            print(f"\nDAILY CANDLES ANALYSIS:")
            
            # Distinct symbols
            symbols = await conn.fetchval("SELECT COUNT(DISTINCT symbol) FROM daily_candles")
            print(f"  Distinct symbols: {symbols}")
            
            # Date range
            date_range = await conn.fetchrow("""
                SELECT MIN(datetime) as min_date, MAX(datetime) as max_date 
                FROM daily_candles
            """)
            print(f"  Date range: {date_range['min_date']} to {date_range['max_date']}")
            
            # Weekly references
            weekly_refs = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NOT NULL")
            print(f"  With weekly references: {weekly_refs} / {daily_count}")
            
        # If we have weekly candles, check details
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        if weekly_count > 0:
            print(f"\nWEEKLY CANDLES ANALYSIS:")
            
            symbols = await conn.fetchval("SELECT COUNT(DISTINCT symbol) FROM weekly_candles")
            print(f"  Distinct symbols: {symbols}")
            
            date_range = await conn.fetchrow("""
                SELECT MIN(week_start_datetime) as min_date, MAX(week_end_datetime) as max_date 
                FROM weekly_candles
            """)
            print(f"  Date range: {date_range['min_date']} to {date_range['max_date']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: Database check failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_database())