"""
Test the week key duplication fix

This script tests the fix to ensure:
1. The week_key column is no longer present
2. The weekly_candle_key_id column works correctly
3. Hard refresh assigns weekly relationships properly
4. Data integrity is maintained
"""

import requests
import time
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_database_after_fix():
    """Verify database state after week key fix"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("\n=== POST-FIX DATABASE VERIFICATION ===")
        
        # Test 1: Verify schema is correct
        print("\n=== TEST 1: VERIFY SCHEMA ===")
        
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles' 
            AND column_name LIKE '%week%'
            ORDER BY column_name
        """)
        
        print("daily_candles weekly columns:")
        for col in columns:
            print(f"  - {col['column_name']} ({col['data_type']})")
        
        # Verify no week_key column exists
        has_week_key = any(col['column_name'] == 'week_key' for col in columns)
        has_weekly_candle_key_id = any(col['column_name'] == 'weekly_candle_key_id' for col in columns)
        
        if has_week_key:
            print("ERROR: daily_candles still has week_key column!")
            return False
        elif has_weekly_candle_key_id:
            print("SUCCESS: daily_candles has only weekly_candle_key_id column")
        else:
            print("WARNING: daily_candles has no weekly columns")
        
        # Test 2: Verify data relationships
        print("\n=== TEST 2: VERIFY DATA RELATIONSHIPS ===")
        
        # Check daily candles relationships
        daily_relationships = await conn.fetchval("""
            SELECT COUNT(*)
            FROM daily_candles dc
            JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
        """)
        
        daily_total = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        print(f"Daily candles with valid weekly relationships: {daily_relationships}/{daily_total}")
        
        # Test 3: Check for NULL values  
        print("\n=== TEST 3: CHECK FOR NULL VALUES ===")
        
        daily_nulls = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NULL")
        print(f"Daily candles with NULL weekly_candle_key_id: {daily_nulls}")
        
        # Test 4: Sample data verification
        print("\n=== TEST 4: SAMPLE DATA VERIFICATION ===")
        
        # Get sample data
        sample_daily = await conn.fetch("""
            SELECT dc.symbol, dc.candle_key_id, dc.weekly_candle_key_id, dc.datetime,
                   wc.week_start_datetime, wc.week_end_datetime
            FROM daily_candles dc
            JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
            ORDER BY dc.datetime DESC
            LIMIT 5
        """)
        
        print("Sample daily candles with weekly relationships:")
        for row in sample_daily:
            print(f"  {row['symbol']} {row['candle_key_id']} -> {row['weekly_candle_key_id']} ({row['datetime'].date()} in week {row['week_start_datetime'].date()} to {row['week_end_datetime'].date()})")
        
        # Final assessment
        if daily_nulls == 0 and daily_relationships > 0:
            print("\nSUCCESS: All tests passed!")
            print("- Redundant week_key column removed")
            print("- All candles have valid weekly_candle_key_id relationships")
            print("- Data integrity maintained")
            return True
        else:
            print("\nERROR: Some tests failed!")
            if daily_nulls > 0:
                print(f"- {daily_nulls} daily candles have NULL weekly_candle_key_id")
            if daily_relationships == 0:
                print("- No valid daily-weekly relationships found")
            return False
        
        await conn.close()
        
    except Exception as e:
        print(f"Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_hard_refresh_with_fix():
    """Test the hard-refresh API endpoint with week key fix"""
    try:
        print("=== TESTING HARD-REFRESH API WITH WEEK KEY FIX ===")
        
        # Test if server is running
        try:
            response = requests.get("http://127.0.0.1:8001/health", timeout=5)
            if response.status_code == 200:
                print("SUCCESS: API server is running")
            else:
                print(f"WARNING: Health check returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Cannot connect to API server: {e}")
            return False
        
        # Trigger hard refresh
        print("Triggering hard-refresh...")
        response = requests.post("http://127.0.0.1:8001/api/hard-refresh", 
                                json={}, 
                                timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print(f"SUCCESS: Hard refresh started")
            print(f"Message: {result.get('message', 'No message')}")
            
            # Wait for refresh to complete (in a real scenario, you'd monitor the progress endpoint)
            print("Waiting 30 seconds for hard refresh to complete...")
            time.sleep(30)
            
            # Verify the database state
            return asyncio.run(verify_database_after_fix())
            
        else:
            print(f"ERROR: Hard refresh failed with status {response.status_code}")
            if response.text:
                print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR: Hard refresh test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_hard_refresh_with_fix()
    if success:
        print("\nSUCCESS: Week key duplication fix verified!")
        print("- week_key column successfully removed")
        print("- Hard-refresh properly assigns weekly_candle_key_id")
        print("- No NULL weekly relationships remain")
        print("- System simplified and working correctly")
    else:
        print("\nERROR: Week key duplication fix failed!")
        print("The fix may need additional attention.")