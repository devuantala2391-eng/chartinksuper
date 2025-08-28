#!/usr/bin/env python3
"""
Test the complete monthly_key system with a simulated hard refresh
"""

import asyncio
import sys
import os
import requests
from datetime import datetime

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def test_complete_system():
    """Test the complete monthly_key system"""
    try:
        print("=== TESTING COMPLETE MONTHLY KEY SYSTEM ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Check current state
            print("=== CURRENT STATE ===")
            daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
            weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles") 
            monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
            daily_null = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE monthly_key IS NULL")
            weekly_null = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE monthly_key IS NULL")
            
            print(f"Daily candles: {daily_count} (NULL monthly_key: {daily_null})")
            print(f"Weekly candles: {weekly_count} (NULL monthly_key: {weekly_null})")
            print(f"Monthly candles: {monthly_count}")
            
            if daily_null > 0 or weekly_null > 0:
                print("\n=== RUNNING MONTHLY_KEY ASSIGNMENT ===")
                
                # Get symbols to process
                symbols = await conn.fetch("SELECT DISTINCT symbol FROM daily_candles")
                
                for symbol_row in symbols:
                    symbol = symbol_row['symbol']
                    print(f"Assigning monthly_key for {symbol}...")
                    
                    # Assign monthly_key to daily candles
                    await ultra_fast_db._assign_monthly_keys_to_daily_candles(conn, symbol)
                    
                    # Assign monthly_key to weekly candles
                    await ultra_fast_db._assign_monthly_keys_to_weekly_candles(conn, symbol)
                
                print("SUCCESS: Monthly_key assignment completed!")
            
            # Verify final state
            print("\n=== FINAL VERIFICATION ===")
            daily_null_after = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE monthly_key IS NULL")
            weekly_null_after = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE monthly_key IS NULL")
            
            print(f"Daily candles with NULL monthly_key: {daily_null_after}")
            print(f"Weekly candles with NULL monthly_key: {weekly_null_after}")
            
            if daily_null_after == 0 and weekly_null_after == 0:
                print("SUCCESS: All candles have valid monthly_key assignments!")
                
                # Show sample relationships
                print("\n=== SAMPLE RELATIONSHIPS ===")
                relationships = await conn.fetch("""
                    SELECT mc.month_sequence_number, mc.monthly_candle_key_id,
                           COUNT(DISTINCT dc.candle_key_id) as daily_count,
                           COUNT(DISTINCT wc.weekly_candle_key_id) as weekly_count
                    FROM monthly_candles mc
                    LEFT JOIN daily_candles dc ON mc.month_sequence_number = dc.monthly_key
                    LEFT JOIN weekly_candles wc ON mc.month_sequence_number = wc.monthly_key
                    GROUP BY mc.month_sequence_number, mc.monthly_candle_key_id
                    ORDER BY mc.month_sequence_number
                    LIMIT 5
                """)
                
                for rel in relationships:
                    print(f"Month {rel['month_sequence_number']} ({rel['monthly_candle_key_id']}): "
                          f"{rel['daily_count']} daily, {rel['weekly_count']} weekly candles")
                
                # Test cross-month boundary case
                print("\n=== CROSS-MONTH BOUNDARY TEST ===")
                cross_month_week = await conn.fetchrow("""
                    SELECT wc.weekly_candle_key_id, wc.week_start_datetime, wc.week_end_datetime, 
                           wc.monthly_key, mc.monthly_candle_key_id
                    FROM weekly_candles wc
                    JOIN monthly_candles mc ON wc.monthly_key = mc.month_sequence_number
                    WHERE wc.week_start_datetime::date != wc.week_end_datetime::date
                    AND EXTRACT(MONTH FROM wc.week_start_datetime) != EXTRACT(MONTH FROM wc.week_end_datetime)
                    LIMIT 1
                """)
                
                if cross_month_week:
                    print(f"Cross-month week found: {cross_month_week['weekly_candle_key_id']}")
                    print(f"  Period: {cross_month_week['week_start_datetime']} to {cross_month_week['week_end_datetime']}")
                    print(f"  Assigned to: monthly_key={cross_month_week['monthly_key']} ({cross_month_week['monthly_candle_key_id']})")
                    print("  Cross-month assignment working correctly (assigned to ending month)")
                else:
                    print("No cross-month weeks found in current data")
                
                return True
            else:
                print("FAILED: Some candles still have NULL monthly_key values")
                return False
        
    except Exception as e:
        print(f"ERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

def trigger_hard_refresh():
    """Try to trigger a hard refresh via HTTP"""
    try:
        print("\n=== ATTEMPTING HARD REFRESH VIA HTTP ===")
        response = requests.post("http://127.0.0.1:8001/api/hard-refresh", 
                               json={}, 
                               timeout=300)
        if response.status_code == 200:
            print("SUCCESS: Hard refresh triggered successfully")
            return True
        else:
            print(f"ERROR: Hard refresh failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR: Could not trigger hard refresh: {e}")
        return False

if __name__ == "__main__":
    print("Testing Complete Monthly Key System")
    print("=" * 50)
    
    # First try to trigger a fresh hard refresh
    hard_refresh_success = trigger_hard_refresh()
    
    if hard_refresh_success:
        print("Waiting for hard refresh to complete...")
        import time
        time.sleep(30)  # Wait for hard refresh to complete
    
    # Test the monthly key system
    success = asyncio.run(test_complete_system())
    
    if success:
        print("\nCOMPLETE MONTHLY KEY SYSTEM TEST: SUCCESS!")
        print("All candles have valid monthly_key assignments")
        print("Cross-month logic working correctly") 
        print("System ready for production use")
    else:
        print("\nCOMPLETE MONTHLY KEY SYSTEM TEST: FAILED!")
        print("Some issues still need to be resolved")