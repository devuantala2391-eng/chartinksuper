#!/usr/bin/env python3
"""
Add monthly_key columns to daily_candles and weekly_candles tables
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def add_monthly_key_columns():
    """Add monthly_key columns to daily_candles and weekly_candles tables"""
    try:
        print("=== ADDING MONTHLY_KEY COLUMNS ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Check if columns already exist
            print("Checking if columns already exist...")
            
            daily_columns = await conn.fetch("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'daily_candles' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
            """)
            
            weekly_columns = await conn.fetch("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'weekly_candles' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
            """)
            
            daily_has_monthly_key = any(col['column_name'] == 'monthly_key' for col in daily_columns)
            daily_has_monthly_key_id = any(col['column_name'] == 'monthly_candle_key_id' for col in daily_columns)
            weekly_has_monthly_key = any(col['column_name'] == 'monthly_key' for col in weekly_columns)
            weekly_has_monthly_key_id = any(col['column_name'] == 'monthly_candle_key_id' for col in weekly_columns)
            
            print(f"Daily candles - monthly_key exists: {daily_has_monthly_key}")
            print(f"Daily candles - monthly_candle_key_id exists: {daily_has_monthly_key_id}")
            print(f"Weekly candles - monthly_key exists: {weekly_has_monthly_key}")
            print(f"Weekly candles - monthly_candle_key_id exists: {weekly_has_monthly_key_id}")
            
            # Add columns to daily_candles table
            print("\n=== ADDING COLUMNS TO DAILY_CANDLES ===")
            if not daily_has_monthly_key:
                await conn.execute("ALTER TABLE daily_candles ADD COLUMN monthly_key INTEGER")
                print("SUCCESS: Added monthly_key column to daily_candles")
            else:
                print("SKIP: monthly_key column already exists in daily_candles")
                
            if not daily_has_monthly_key_id:
                await conn.execute("ALTER TABLE daily_candles ADD COLUMN monthly_candle_key_id VARCHAR(50)")
                print("SUCCESS: Added monthly_candle_key_id column to daily_candles")
            else:
                print("SKIP: monthly_candle_key_id column already exists in daily_candles")
            
            # Add columns to weekly_candles table
            print("\n=== ADDING COLUMNS TO WEEKLY_CANDLES ===")
            if not weekly_has_monthly_key:
                await conn.execute("ALTER TABLE weekly_candles ADD COLUMN monthly_key INTEGER")
                print("SUCCESS: Added monthly_key column to weekly_candles")
            else:
                print("SKIP: monthly_key column already exists in weekly_candles")
                
            if not weekly_has_monthly_key_id:
                await conn.execute("ALTER TABLE weekly_candles ADD COLUMN monthly_candle_key_id VARCHAR(50)")
                print("SUCCESS: Added monthly_candle_key_id column to weekly_candles")
            else:
                print("SKIP: monthly_candle_key_id column already exists in weekly_candles")
            
            # Create indexes for performance
            print("\n=== CREATING INDEXES ===")
            try:
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_monthly_key ON daily_candles(monthly_key)")
                print("SUCCESS: Created index on daily_candles.monthly_key")
                
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_monthly_key_id ON daily_candles(monthly_candle_key_id)")
                print("SUCCESS: Created index on daily_candles.monthly_candle_key_id")
                
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_weekly_monthly_key ON weekly_candles(monthly_key)")
                print("SUCCESS: Created index on weekly_candles.monthly_key")
                
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_weekly_monthly_key_id ON weekly_candles(monthly_candle_key_id)")
                print("SUCCESS: Created index on weekly_candles.monthly_candle_key_id")
            except Exception as e:
                print(f"Index creation warning: {e}")
            
            print("\n=== VERIFYING NEW STRUCTURE ===")
            # Verify daily_candles structure
            daily_structure = await conn.fetch("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'daily_candles' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
                ORDER BY column_name
            """)
            
            print("Daily candles new columns:")
            for col in daily_structure:
                nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
                print(f"  {col['column_name']}: {col['data_type']} ({nullable})")
            
            # Verify weekly_candles structure
            weekly_structure = await conn.fetch("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'weekly_candles' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
                ORDER BY column_name
            """)
            
            print("\nWeekly candles new columns:")
            for col in weekly_structure:
                nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
                print(f"  {col['column_name']}: {col['data_type']} ({nullable})")
            
            print("\nMONTHLY_KEY COLUMNS SUCCESSFULLY ADDED!")
        
    except Exception as e:
        print(f"ERROR: Failed to add columns: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(add_monthly_key_columns())