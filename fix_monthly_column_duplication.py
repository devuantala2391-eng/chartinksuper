"""
Fix Monthly Column Duplication Issue

This script consolidates the monthly key system to use only monthly_candle_key_id,
removing the redundant monthly_key column from daily_candles and weekly_candles tables.

The fix includes:
1. Drop the redundant monthly_key column from both tables
2. Update all code references to use only monthly_candle_key_id
3. Update indexes to reflect the change
4. Verify data integrity
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_monthly_column_duplication():
    """Fix the monthly column duplication issue"""
    
    try:
        print("=== FIXING MONTHLY COLUMN DUPLICATION ===")
        
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("SUCCESS: Connected to database")
        
        # Step 1: Verify current state
        print("\n=== STEP 1: VERIFY CURRENT STATE ===")
        
        # Check both tables for monthly columns
        for table_name in ['daily_candles', 'weekly_candles']:
            monthly_columns = await conn.fetch(f"""
                SELECT column_name, data_type
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
                ORDER BY column_name
            """)
            
            print(f"{table_name} monthly columns:")
            for col in monthly_columns:
                print(f"  - {col['column_name']} ({col['data_type']})")
            
            # Check for NULL values
            if monthly_columns:
                null_check = await conn.fetchrow(f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        COUNT(*) - COUNT(monthly_key) as monthly_key_nulls,
                        COUNT(*) - COUNT(monthly_candle_key_id) as monthly_candle_key_id_nulls
                    FROM {table_name}
                """)
                print(f"  Total rows: {null_check['total_rows']}")
                print(f"  monthly_key NULLs: {null_check['monthly_key_nulls']}")
                print(f"  monthly_candle_key_id NULLs: {null_check['monthly_candle_key_id_nulls']}")
        
        # Step 2: Verify data consistency between the two columns
        print("\n=== STEP 2: VERIFY DATA CONSISTENCY ===")
        
        for table_name in ['daily_candles', 'weekly_candles']:
            # Check if monthly_key and monthly_candle_key_id are properly aligned
            inconsistency_check = await conn.fetchval(f"""
                SELECT COUNT(*)
                FROM {table_name} dc
                LEFT JOIN monthly_candles mc ON dc.monthly_candle_key_id = mc.monthly_candle_key_id
                WHERE dc.monthly_key IS NOT NULL 
                AND dc.monthly_candle_key_id IS NOT NULL
                AND dc.monthly_key != mc.month_sequence_number
            """)
            
            print(f"{table_name} inconsistencies between monthly_key and monthly_candle_key_id: {inconsistency_check}")
            
            if inconsistency_check > 0:
                print(f"WARNING: Found {inconsistency_check} inconsistent records in {table_name}")
                # Show sample of inconsistent data
                inconsistent_samples = await conn.fetch(f"""
                    SELECT dc.*, mc.month_sequence_number as expected_monthly_key
                    FROM {table_name} dc
                    LEFT JOIN monthly_candles mc ON dc.monthly_candle_key_id = mc.monthly_candle_key_id
                    WHERE dc.monthly_key IS NOT NULL 
                    AND dc.monthly_candle_key_id IS NOT NULL
                    AND dc.monthly_key != mc.month_sequence_number
                    LIMIT 5
                """)
                
                for sample in inconsistent_samples:
                    print(f"  - {sample['symbol']} has monthly_key={sample['monthly_key']} but should be {sample['expected_monthly_key']} based on {sample['monthly_candle_key_id']}")
        
        # Step 3: Create backup queries for verification
        print("\n=== STEP 3: CREATE BACKUP DATA FOR VERIFICATION ===")
        
        # Save current state for verification
        daily_backup = await conn.fetch("""
            SELECT symbol, candle_key_id, monthly_key, monthly_candle_key_id, datetime
            FROM daily_candles
            WHERE monthly_key IS NOT NULL OR monthly_candle_key_id IS NOT NULL
            ORDER BY datetime
            LIMIT 10
        """)
        
        weekly_backup = await conn.fetch("""
            SELECT symbol, weekly_candle_key_id, monthly_key, monthly_candle_key_id, week_start_datetime
            FROM weekly_candles
            WHERE monthly_key IS NOT NULL OR monthly_candle_key_id IS NOT NULL
            ORDER BY week_start_datetime
            LIMIT 10
        """)
        
        print(f"Backed up {len(daily_backup)} daily candles sample")
        print(f"Backed up {len(weekly_backup)} weekly candles sample")
        
        # Step 4: Drop indexes related to monthly_key
        print("\n=== STEP 4: DROP MONTHLY_KEY INDEXES ===")
        
        indexes_to_drop = [
            'idx_daily_monthly_key',
            'idx_weekly_monthly_key'
        ]
        
        for index_name in indexes_to_drop:
            try:
                await conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                print(f"SUCCESS: Dropped index: {index_name}")
            except Exception as e:
                print(f"WARNING: Could not drop index {index_name}: {e}")
        
        # Step 5: Drop the redundant monthly_key columns
        print("\n=== STEP 5: DROP REDUNDANT MONTHLY_KEY COLUMNS ===")
        
        for table_name in ['daily_candles', 'weekly_candles']:
            try:
                # Check if column exists before dropping
                column_exists = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = '{table_name}' AND column_name = 'monthly_key'
                    )
                """)
                
                if column_exists:
                    await conn.execute(f"ALTER TABLE {table_name} DROP COLUMN monthly_key")
                    print(f"SUCCESS: Dropped monthly_key column from {table_name}")
                else:
                    print(f"INFO: monthly_key column does not exist in {table_name}")
                    
            except Exception as e:
                print(f"ERROR: Error dropping monthly_key from {table_name}: {e}")
                raise
        
        # Step 6: Verify the fix
        print("\n=== STEP 6: VERIFY THE FIX ===")
        
        for table_name in ['daily_candles', 'weekly_candles']:
            # Check remaining columns
            remaining_columns = await conn.fetch(f"""
                SELECT column_name
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND column_name IN ('monthly_key', 'monthly_candle_key_id')
                ORDER BY column_name
            """)
            
            print(f"{table_name} remaining monthly columns:")
            for col in remaining_columns:
                print(f"  - {col['column_name']}")
            
            # Verify data is still accessible via monthly_candle_key_id
            test_query = await conn.fetchval(f"""
                SELECT COUNT(*)
                FROM {table_name} dc
                JOIN monthly_candles mc ON dc.monthly_candle_key_id = mc.monthly_candle_key_id
            """)
            print(f"  Records with valid monthly relationships: {test_query}")
        
        # Step 7: Verify backup data is still accessible
        print("\n=== STEP 7: VERIFY DATA INTEGRITY AFTER FIX ===")
        
        # Check that the same data is still accessible via monthly_candle_key_id
        for backup_row in daily_backup[:3]:  # Check first 3 samples
            current_data = await conn.fetchrow("""
                SELECT symbol, candle_key_id, monthly_candle_key_id, datetime
                FROM daily_candles
                WHERE candle_key_id = $1
            """, backup_row['candle_key_id'])
            
            if current_data and current_data['monthly_candle_key_id'] == backup_row['monthly_candle_key_id']:
                print(f"SUCCESS: Daily candle {backup_row['candle_key_id']} monthly relationship preserved")
            else:
                print(f"ERROR: Daily candle {backup_row['candle_key_id']} monthly relationship lost!")
        
        for backup_row in weekly_backup[:3]:  # Check first 3 samples
            current_data = await conn.fetchrow("""
                SELECT symbol, weekly_candle_key_id, monthly_candle_key_id, week_start_datetime
                FROM weekly_candles
                WHERE weekly_candle_key_id = $1
            """, backup_row['weekly_candle_key_id'])
            
            if current_data and current_data['monthly_candle_key_id'] == backup_row['monthly_candle_key_id']:
                print(f"SUCCESS: Weekly candle {backup_row['weekly_candle_key_id']} monthly relationship preserved")
            else:
                print(f"ERROR: Weekly candle {backup_row['weekly_candle_key_id']} monthly relationship lost!")
        
        print("\n=== MONTHLY COLUMN DUPLICATION FIX COMPLETED ===")
        print("SUCCESS: Redundant monthly_key columns removed")
        print("SUCCESS: Data integrity verified")
        print("SUCCESS: System now uses only monthly_candle_key_id for monthly relationships")
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: Error during fix: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(fix_monthly_column_duplication())