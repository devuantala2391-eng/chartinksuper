#!/usr/bin/env python3
"""
Quick test to check monthly candles generation
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def test_monthly_candles():
    """Test monthly candles generation"""
    try:
        print("Initializing database connection...")
        await ultra_fast_db.initialize()
        
        # Check if we have monthly candles
        async with ultra_fast_db.pool.acquire() as conn:
            monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
            print(f"Monthly candles in database: {monthly_count}")
            
            if monthly_count == 0:
                print("No monthly candles found. Testing generation...")
                
                # Generate monthly candles for 20MICRONS
                success = await ultra_fast_db.generate_monthly_candles_for_symbol("20MICRONS")
                print(f"Monthly generation result: {success}")
                
                # Check count again
                monthly_count_after = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles WHERE symbol = '20MICRONS'")
                print(f"Monthly candles for 20MICRONS after generation: {monthly_count_after}")
                
                if monthly_count_after > 0:
                    # Show some sample data
                    sample = await conn.fetchrow("SELECT * FROM monthly_candles WHERE symbol = '20MICRONS' ORDER BY month_start_timestamp DESC LIMIT 1")
                    print(f"Latest monthly candle: {dict(sample)}")
            else:
                print("Monthly candles already exist!")
                sample = await conn.fetchrow("SELECT COUNT(*), MIN(month_start_timestamp), MAX(month_start_timestamp) FROM monthly_candles")
                print(f"Total: {sample['count']}, Date range: {sample['min']} to {sample['max']}")
        
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(test_monthly_candles())