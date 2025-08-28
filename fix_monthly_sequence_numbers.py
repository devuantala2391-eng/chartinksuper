#!/usr/bin/env python3
"""
Fix month_sequence_number to start from 0 in monthly_candles table
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def fix_monthly_sequence_numbers():
    """Fix month_sequence_number to start from 0"""
    try:
        print("=== FIXING MONTHLY SEQUENCE NUMBERS TO START FROM 0 ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Check current sequence numbers
            print("Checking current monthly sequence numbers...")
            current_sequences = await conn.fetch("""
                SELECT monthly_candle_key_id, symbol, month_sequence_number, month_start_datetime
                FROM monthly_candles 
                ORDER BY month_start_timestamp
            """)
            
            print("BEFORE - Current sequence numbers:")
            for seq in current_sequences:
                print(f"  {seq['monthly_candle_key_id']}: seq={seq['month_sequence_number']}, date={seq['month_start_datetime']}")
            
            if not current_sequences:
                print("No monthly candles found!")
                return
            
            # Check if already starting from 0
            min_sequence = min(seq['month_sequence_number'] for seq in current_sequences)
            print(f"\nMinimum sequence number: {min_sequence}")
            
            if min_sequence == 0:
                print("SKIP: Monthly sequence numbers already start from 0!")
                return
            
            # Update all sequence numbers to start from 0
            print(f"\nUpdating all sequence numbers (subtracting {min_sequence})...")
            
            update_count = await conn.execute("""
                UPDATE monthly_candles 
                SET month_sequence_number = month_sequence_number - $1
            """, min_sequence)
            
            print(f"SUCCESS: Updated {update_count} monthly candles")
            
            # Verify the changes
            print("\nVerifying updated sequence numbers...")
            updated_sequences = await conn.fetch("""
                SELECT monthly_candle_key_id, symbol, month_sequence_number, month_start_datetime
                FROM monthly_candles 
                ORDER BY month_start_timestamp
            """)
            
            print("AFTER - Updated sequence numbers:")
            for seq in updated_sequences:
                print(f"  {seq['monthly_candle_key_id']}: seq={seq['month_sequence_number']}, date={seq['month_start_datetime']}")
            
            # Verify sequence continuity (should be 0, 1, 2, 3, ...)
            expected_sequences = list(range(len(updated_sequences)))
            actual_sequences = sorted([seq['month_sequence_number'] for seq in updated_sequences])
            
            print(f"\nSequence verification:")
            print(f"Expected: {expected_sequences}")
            print(f"Actual:   {actual_sequences}")
            
            if actual_sequences == expected_sequences:
                print("SUCCESS: Monthly sequence numbers are now continuous starting from 0!")
            else:
                print("WARNING: Sequence numbers are not continuous!")
            
            print("\nMONTHLY SEQUENCE NUMBERS SUCCESSFULLY FIXED!")
        
    except Exception as e:
        print(f"ERROR: Failed to fix sequence numbers: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(fix_monthly_sequence_numbers())