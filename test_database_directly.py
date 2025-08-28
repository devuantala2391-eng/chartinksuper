"""
Test database directly after week key fix
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_database_directly():
    """Test database state directly"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("=== DIRECT DATABASE VERIFICATION ===")
        
        # Test 1: Check table schema
        print("\n=== SCHEMA CHECK ===")
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles'
            ORDER BY ordinal_position
        """)
        
        print(f"Daily candles table now has {len(columns)} columns:")
        weekly_columns = []
        for col in columns:
            if 'week' in col['column_name'].lower():
                weekly_columns.append(col['column_name'])
            print(f"  {col['column_name']:25} {col['data_type']}")
        
        print(f"\nWeekly-related columns: {weekly_columns}")
        
        # Test 2: Check data
        print("\n=== DATA CHECK ===")
        total_daily = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        weekly_assigned = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NOT NULL")
        weekly_null = total_daily - weekly_assigned
        
        print(f"Daily candles: {total_daily} total")
        print(f"With weekly_candle_key_id: {weekly_assigned}")
        print(f"NULL weekly_candle_key_id: {weekly_null}")
        
        # Test 3: Check relationships
        print("\n=== RELATIONSHIP CHECK ===")
        valid_relationships = await conn.fetchval("""
            SELECT COUNT(*)
            FROM daily_candles dc
            JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
        """)
        
        print(f"Valid daily->weekly relationships: {valid_relationships}")
        
        # Test 4: Sample data
        print("\n=== SAMPLE DATA ===")
        samples = await conn.fetch("""
            SELECT dc.symbol, dc.candle_key_id, dc.weekly_candle_key_id, dc.day_of_week, dc.datetime
            FROM daily_candles dc
            ORDER BY dc.datetime DESC
            LIMIT 5
        """)
        
        for row in samples:
            print(f"  {row['symbol']} {row['candle_key_id']} -> {row['weekly_candle_key_id']} (day {row['day_of_week']}) {row['datetime'].date()}")
        
        await conn.close()
        
        # Final result
        has_week_key = 'week_key' in weekly_columns
        has_weekly_candle_key_id = 'weekly_candle_key_id' in weekly_columns
        
        if not has_week_key and has_weekly_candle_key_id and weekly_null == 0:
            print("\nSUCCESS: Week key fix is working correctly!")
            return True
        else:
            print("\nERROR: Week key fix has issues!")
            if has_week_key:
                print("- week_key column still exists")
            if not has_weekly_candle_key_id:
                print("- weekly_candle_key_id column missing")
            if weekly_null > 0:
                print(f"- {weekly_null} candles have NULL weekly_candle_key_id")
            return False
        
    except Exception as e:
        print(f"Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_database_directly())
    if success:
        print("\nDATABASE TEST: PASSED")
    else:
        print("\nDATABASE TEST: FAILED")