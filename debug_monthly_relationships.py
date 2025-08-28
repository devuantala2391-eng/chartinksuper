#!/usr/bin/env python3
"""
Debug the monthly key relationships to ensure they're correct
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def debug_monthly_relationships():
    """Debug monthly key relationships"""
    try:
        print("=== DEBUGGING MONTHLY KEY RELATIONSHIPS ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Check detailed relationships for first few months
            print("=== DETAILED MONTHLY RELATIONSHIPS ===")
            
            for month_key in [0, 1, 2]:
                print(f"\n--- MONTH {month_key} ---")
                
                # Get monthly candle info
                monthly_info = await conn.fetchrow("""
                    SELECT monthly_candle_key_id, month_start_datetime, month_end_datetime
                    FROM monthly_candles 
                    WHERE month_sequence_number = $1
                """, month_key)
                
                if monthly_info:
                    print(f"Monthly: {monthly_info['monthly_candle_key_id']}")
                    print(f"Period: {monthly_info['month_start_datetime'].strftime('%Y-%m-%d')} to {monthly_info['month_end_datetime'].strftime('%Y-%m-%d')}")
                
                # Count daily candles for this month
                daily_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM daily_candles WHERE monthly_key = $1
                """, month_key)
                print(f"Daily candles: {daily_count}")
                
                # Count weekly candles for this month  
                weekly_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM weekly_candles WHERE monthly_key = $1
                """, month_key)
                print(f"Weekly candles: {weekly_count}")
                
                # Show sample daily candles
                daily_samples = await conn.fetch("""
                    SELECT candle_key_id, datetime, monthly_key, monthly_candle_key_id
                    FROM daily_candles 
                    WHERE monthly_key = $1
                    ORDER BY datetime
                    LIMIT 3
                """, month_key)
                
                print("Sample daily candles:")
                for sample in daily_samples:
                    print(f"  {sample['candle_key_id']}: {sample['datetime'].strftime('%Y-%m-%d')} -> monthly_key={sample['monthly_key']}")
                
                # Show sample weekly candles
                weekly_samples = await conn.fetch("""
                    SELECT weekly_candle_key_id, week_start_datetime, week_end_datetime, monthly_key, monthly_candle_key_id
                    FROM weekly_candles 
                    WHERE monthly_key = $1
                    ORDER BY week_start_datetime
                    LIMIT 3
                """, month_key)
                
                print("Sample weekly candles:")
                for sample in weekly_samples:
                    print(f"  {sample['weekly_candle_key_id']}: {sample['week_start_datetime'].strftime('%Y-%m-%d')} to {sample['week_end_datetime'].strftime('%Y-%m-%d')} -> monthly_key={sample['monthly_key']}")
            
            # Check for any NULL monthly_key values
            print("\n=== CHECKING FOR NULL VALUES ===")
            
            daily_null_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE monthly_key IS NULL")
            weekly_null_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE monthly_key IS NULL")
            
            print(f"Daily candles with NULL monthly_key: {daily_null_count}")
            print(f"Weekly candles with NULL monthly_key: {weekly_null_count}")
            
            if daily_null_count > 0:
                null_daily_samples = await conn.fetch("""
                    SELECT candle_key_id, datetime FROM daily_candles 
                    WHERE monthly_key IS NULL 
                    ORDER BY datetime LIMIT 5
                """)
                print("Sample daily candles with NULL monthly_key:")
                for sample in null_daily_samples:
                    print(f"  {sample['candle_key_id']}: {sample['datetime']}")
            
            if weekly_null_count > 0:
                null_weekly_samples = await conn.fetch("""
                    SELECT weekly_candle_key_id, week_start_datetime, week_end_datetime 
                    FROM weekly_candles 
                    WHERE monthly_key IS NULL 
                    ORDER BY week_start_datetime LIMIT 5
                """)
                print("Sample weekly candles with NULL monthly_key:")
                for sample in null_weekly_samples:
                    print(f"  {sample['weekly_candle_key_id']}: {sample['week_start_datetime']} to {sample['week_end_datetime']}")
            
            # Show overall distribution
            print("\n=== OVERALL DISTRIBUTION ===")
            distribution = await conn.fetch("""
                SELECT monthly_key, COUNT(*) as count
                FROM (
                    SELECT monthly_key FROM daily_candles
                    UNION ALL 
                    SELECT monthly_key FROM weekly_candles
                ) combined
                WHERE monthly_key IS NOT NULL
                GROUP BY monthly_key
                ORDER BY monthly_key
            """)
            
            for dist in distribution:
                print(f"Month {dist['monthly_key']}: {dist['count']} total candles (daily + weekly)")
        
    except Exception as e:
        print(f"ERROR: Debug failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(debug_monthly_relationships())