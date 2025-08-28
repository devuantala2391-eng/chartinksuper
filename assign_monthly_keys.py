#!/usr/bin/env python3
"""
Assign monthly_key and monthly_candle_key_id to existing daily and weekly candles
Based on the month where the period ENDS (per user requirement)
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def assign_monthly_keys():
    """Assign monthly_key to all existing daily and weekly candles"""
    try:
        print("=== ASSIGNING MONTHLY_KEYS TO EXISTING DATA ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # First, get all monthly candles for reference
            print("Loading monthly candles reference data...")
            monthly_candles = await conn.fetch("""
                SELECT monthly_candle_key_id, symbol, month_sequence_number, 
                       month_start_datetime, month_end_datetime
                FROM monthly_candles 
                ORDER BY month_start_datetime
            """)
            
            if not monthly_candles:
                print("ERROR: No monthly candles found! Need monthly candles as reference.")
                return
            
            print(f"Found {len(monthly_candles)} monthly candles for reference:")
            for mc in monthly_candles:
                print(f"  {mc['monthly_candle_key_id']}: seq={mc['month_sequence_number']}, "
                      f"{mc['month_start_datetime'].strftime('%Y-%m-%d')} to {mc['month_end_datetime'].strftime('%Y-%m-%d')}")
            
            # === ASSIGN MONTHLY_KEY TO DAILY CANDLES ===
            print("\n=== ASSIGNING MONTHLY_KEY TO DAILY CANDLES ===")
            
            # Get all daily candles
            daily_candles = await conn.fetch("""
                SELECT candle_key_id, symbol, datetime, monthly_key, monthly_candle_key_id
                FROM daily_candles 
                ORDER BY datetime
            """)
            
            print(f"Processing {len(daily_candles)} daily candles...")
            
            daily_updates = 0
            for daily in daily_candles:
                daily_datetime = daily['datetime']
                daily_symbol = daily['symbol']
                
                # Find which monthly candle this daily candle belongs to
                # Daily candles are assigned based on their exact date
                assigned_monthly = None
                for mc in monthly_candles:
                    if (mc['symbol'] == daily_symbol and 
                        mc['month_start_datetime'].date() <= daily_datetime.date() <= mc['month_end_datetime'].date()):
                        assigned_monthly = mc
                        break
                
                if assigned_monthly:
                    # Update daily candle with monthly_key and monthly_candle_key_id
                    if (daily['monthly_key'] != assigned_monthly['month_sequence_number'] or 
                        daily['monthly_candle_key_id'] != assigned_monthly['monthly_candle_key_id']):
                        
                        await conn.execute("""
                            UPDATE daily_candles 
                            SET monthly_key = $1, monthly_candle_key_id = $2
                            WHERE candle_key_id = $3
                        """, assigned_monthly['month_sequence_number'], 
                             assigned_monthly['monthly_candle_key_id'], 
                             daily['candle_key_id'])
                        
                        daily_updates += 1
                        
                        if daily_updates <= 5:  # Show first 5 updates as examples
                            print(f"  Daily {daily['candle_key_id']}: {daily_datetime.strftime('%Y-%m-%d')} -> "
                                  f"monthly_key={assigned_monthly['month_sequence_number']}, "
                                  f"monthly_id={assigned_monthly['monthly_candle_key_id']}")
                else:
                    print(f"WARNING: No monthly candle found for daily {daily['candle_key_id']} on {daily_datetime}")
            
            print(f"SUCCESS: Updated {daily_updates} daily candles with monthly_key")
            
            # === ASSIGN MONTHLY_KEY TO WEEKLY CANDLES ===
            print("\n=== ASSIGNING MONTHLY_KEY TO WEEKLY CANDLES ===")
            
            # Get all weekly candles
            weekly_candles = await conn.fetch("""
                SELECT weekly_candle_key_id, symbol, week_start_datetime, week_end_datetime, 
                       monthly_key, monthly_candle_key_id
                FROM weekly_candles 
                ORDER BY week_start_datetime
            """)
            
            print(f"Processing {len(weekly_candles)} weekly candles...")
            
            weekly_updates = 0
            for weekly in weekly_candles:
                # For weekly candles, assign based on where the week ENDS (per user requirement)
                week_end_datetime = weekly['week_end_datetime']
                weekly_symbol = weekly['symbol']
                
                # Find which monthly candle this weekly candle belongs to (based on end date)
                assigned_monthly = None
                for mc in monthly_candles:
                    if (mc['symbol'] == weekly_symbol and 
                        mc['month_start_datetime'].date() <= week_end_datetime.date() <= mc['month_end_datetime'].date()):
                        assigned_monthly = mc
                        break
                
                if assigned_monthly:
                    # Update weekly candle with monthly_key and monthly_candle_key_id
                    if (weekly['monthly_key'] != assigned_monthly['month_sequence_number'] or 
                        weekly['monthly_candle_key_id'] != assigned_monthly['monthly_candle_key_id']):
                        
                        await conn.execute("""
                            UPDATE weekly_candles 
                            SET monthly_key = $1, monthly_candle_key_id = $2
                            WHERE weekly_candle_key_id = $3
                        """, assigned_monthly['month_sequence_number'], 
                             assigned_monthly['monthly_candle_key_id'], 
                             weekly['weekly_candle_key_id'])
                        
                        weekly_updates += 1
                        
                        if weekly_updates <= 5:  # Show first 5 updates as examples
                            print(f"  Weekly {weekly['weekly_candle_key_id']}: "
                                  f"ends {week_end_datetime.strftime('%Y-%m-%d')} -> "
                                  f"monthly_key={assigned_monthly['month_sequence_number']}, "
                                  f"monthly_id={assigned_monthly['monthly_candle_key_id']}")
                else:
                    print(f"WARNING: No monthly candle found for weekly {weekly['weekly_candle_key_id']} "
                          f"ending on {week_end_datetime}")
            
            print(f"SUCCESS: Updated {weekly_updates} weekly candles with monthly_key")
            
            # === VERIFICATION ===
            print("\n=== VERIFICATION ===")
            
            # Check daily candles assignment
            daily_stats = await conn.fetchrow("""
                SELECT COUNT(*) as total, 
                       COUNT(monthly_key) as with_monthly_key,
                       COUNT(monthly_candle_key_id) as with_monthly_key_id
                FROM daily_candles
            """)
            print(f"Daily candles: {daily_stats['total']} total, "
                  f"{daily_stats['with_monthly_key']} with monthly_key, "
                  f"{daily_stats['with_monthly_key_id']} with monthly_candle_key_id")
            
            # Check weekly candles assignment  
            weekly_stats = await conn.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(monthly_key) as with_monthly_key,
                       COUNT(monthly_candle_key_id) as with_monthly_key_id
                FROM weekly_candles
            """)
            print(f"Weekly candles: {weekly_stats['total']} total, "
                  f"{weekly_stats['with_monthly_key']} with monthly_key, "
                  f"{weekly_stats['with_monthly_key_id']} with monthly_candle_key_id")
            
            # Show sample relationships
            print("\n=== SAMPLE RELATIONSHIPS ===")
            relationships = await conn.fetch("""
                SELECT mc.month_sequence_number, mc.monthly_candle_key_id,
                       COUNT(dc.candle_key_id) as daily_count,
                       COUNT(wc.weekly_candle_key_id) as weekly_count
                FROM monthly_candles mc
                LEFT JOIN daily_candles dc ON mc.month_sequence_number = dc.monthly_key
                LEFT JOIN weekly_candles wc ON mc.month_sequence_number = wc.monthly_key
                GROUP BY mc.month_sequence_number, mc.monthly_candle_key_id
                ORDER BY mc.month_sequence_number
                LIMIT 5
            """)
            
            for rel in relationships:
                print(f"Month {rel['month_sequence_number']} ({rel['monthly_candle_key_id']}): "
                      f"{rel['daily_count']} daily candles, {rel['weekly_count']} weekly candles")
            
            print("\nMONTHLY_KEY ASSIGNMENT COMPLETED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"ERROR: Failed to assign monthly keys: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(assign_monthly_keys())