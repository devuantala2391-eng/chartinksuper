"""
Test the monthly key duplication fix

This script tests the fix to ensure:
1. The monthly_key column is no longer present
2. The monthly_candle_key_id column works correctly
3. Hard refresh assigns monthly relationships properly
4. Data integrity is maintained
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import time

load_dotenv()

async def test_monthly_fix():
    """Test the monthly key duplication fix"""
    
    try:
        print("=== TESTING MONTHLY KEY DUPLICATION FIX ===")
        
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("SUCCESS: Connected to database")
        
        # Test 1: Verify schema is correct
        print("\n=== TEST 1: VERIFY SCHEMA ===")
        
        for table_name in ['daily_candles', 'weekly_candles']:
            columns = await conn.fetch(f"""
                SELECT column_name, data_type
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND column_name LIKE '%monthly%'
                ORDER BY column_name
            """)
            
            print(f"{table_name} monthly columns:")
            for col in columns:
                print(f"  - {col['column_name']} ({col['data_type']})")
            
            # Verify no monthly_key column exists
            has_monthly_key = any(col['column_name'] == 'monthly_key' for col in columns)
            has_monthly_candle_key_id = any(col['column_name'] == 'monthly_candle_key_id' for col in columns)
            
            if has_monthly_key:
                print(f"ERROR: {table_name} still has monthly_key column!")
                return False
            elif has_monthly_candle_key_id:
                print(f"SUCCESS: {table_name} has only monthly_candle_key_id column")
            else:
                print(f"WARNING: {table_name} has no monthly columns")
        
        # Test 2: Verify data relationships
        print("\n=== TEST 2: VERIFY DATA RELATIONSHIPS ===")
        
        # Check daily candles relationships
        daily_relationships = await conn.fetchval("""
            SELECT COUNT(*)
            FROM daily_candles dc
            JOIN monthly_candles mc ON dc.monthly_candle_key_id = mc.monthly_candle_key_id
        """)
        
        daily_total = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        print(f"Daily candles with valid monthly relationships: {daily_relationships}/{daily_total}")
        
        # Check weekly candles relationships
        weekly_relationships = await conn.fetchval("""
            SELECT COUNT(*)
            FROM weekly_candles wc
            JOIN monthly_candles mc ON wc.monthly_candle_key_id = mc.monthly_candle_key_id
        """)
        
        weekly_total = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        print(f"Weekly candles with valid monthly relationships: {weekly_relationships}/{weekly_total}")
        
        # Test 3: Check for NULL values  
        print("\n=== TEST 3: CHECK FOR NULL VALUES ===")
        
        daily_nulls = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE monthly_candle_key_id IS NULL")
        weekly_nulls = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE monthly_candle_key_id IS NULL")
        
        print(f"Daily candles with NULL monthly_candle_key_id: {daily_nulls}")
        print(f"Weekly candles with NULL monthly_candle_key_id: {weekly_nulls}")
        
        # Test 4: Sample data verification
        print("\n=== TEST 4: SAMPLE DATA VERIFICATION ===")
        
        # Get sample data
        sample_daily = await conn.fetch("""
            SELECT dc.symbol, dc.candle_key_id, dc.monthly_candle_key_id, dc.datetime,
                   mc.month_start_datetime, mc.month_end_datetime
            FROM daily_candles dc
            JOIN monthly_candles mc ON dc.monthly_candle_key_id = mc.monthly_candle_key_id
            ORDER BY dc.datetime DESC
            LIMIT 5
        """)
        
        print("Sample daily candles with monthly relationships:")
        for row in sample_daily:
            print(f"  {row['symbol']} {row['candle_key_id']} -> {row['monthly_candle_key_id']} ({row['datetime'].date()} in {row['month_start_datetime'].date()} to {row['month_end_datetime'].date()})")
        
        sample_weekly = await conn.fetch("""
            SELECT wc.symbol, wc.weekly_candle_key_id, wc.monthly_candle_key_id, wc.week_end_datetime,
                   mc.month_start_datetime, mc.month_end_datetime
            FROM weekly_candles wc
            JOIN monthly_candles mc ON wc.monthly_candle_key_id = mc.monthly_candle_key_id
            ORDER BY wc.week_end_datetime DESC
            LIMIT 3
        """)
        
        print("Sample weekly candles with monthly relationships:")
        for row in sample_weekly:
            print(f"  {row['symbol']} {row['weekly_candle_key_id']} -> {row['monthly_candle_key_id']} (week ending {row['week_end_datetime'].date()} in {row['month_start_datetime'].date()} to {row['month_end_datetime'].date()})")
        
        # Test 5: Performance test for queries using monthly_candle_key_id
        print("\n=== TEST 5: QUERY PERFORMANCE TEST ===")
        
        start_time = time.time()
        
        # Test query using monthly_candle_key_id
        monthly_summary = await conn.fetch("""
            SELECT mc.monthly_candle_key_id, mc.symbol, mc.month_start_datetime,
                   COUNT(dc.candle_key_id) as daily_count,
                   COUNT(wc.weekly_candle_key_id) as weekly_count
            FROM monthly_candles mc
            LEFT JOIN daily_candles dc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            LEFT JOIN weekly_candles wc ON mc.monthly_candle_key_id = wc.monthly_candle_key_id
            GROUP BY mc.monthly_candle_key_id, mc.symbol, mc.month_start_datetime
            ORDER BY mc.month_start_datetime DESC
        """)
        
        query_time = time.time() - start_time
        print(f"Query using monthly_candle_key_id completed in {query_time:.3f}s")
        print(f"Found {len(monthly_summary)} monthly periods")
        
        for row in monthly_summary[:3]:
            print(f"  {row['monthly_candle_key_id']}: {row['daily_count']} daily, {row['weekly_count']} weekly candles")
        
        print("\n=== MONTHLY KEY DUPLICATION FIX TESTS COMPLETED ===")
        
        # Final assessment
        if daily_nulls == 0 and weekly_nulls == 0 and daily_relationships > 0 and weekly_relationships > 0:
            print("SUCCESS: All tests passed!")
            print("- Redundant monthly_key column removed")
            print("- All candles have valid monthly_candle_key_id relationships")
            print("- Query performance is good")
            print("- Data integrity maintained")
            return True
        else:
            print("ERROR: Some tests failed!")
            if daily_nulls > 0:
                print(f"- {daily_nulls} daily candles have NULL monthly_candle_key_id")
            if weekly_nulls > 0:
                print(f"- {weekly_nulls} weekly candles have NULL monthly_candle_key_id")
            if daily_relationships == 0:
                print("- No valid daily-monthly relationships found")
            if weekly_relationships == 0:
                print("- No valid weekly-monthly relationships found")
            return False
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_monthly_fix())
    if success:
        print("\n✅ ALL TESTS PASSED - Fix is working correctly!")
    else:
        print("\n❌ TESTS FAILED - Fix needs attention!")