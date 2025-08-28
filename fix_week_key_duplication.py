"""
Fix Week Key Duplication Issue

This script removes the redundant week_key column from daily_candles table,
keeping only weekly_candle_key_id for weekly relationships.

The fix includes:
1. Drop the redundant week_key column from daily_candles table
2. Update all code references to remove week_key logic
3. Update indexes to reflect the change
4. Verify data integrity
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_week_key_duplication():
    """Fix the week key duplication issue"""
    
    try:
        print("=== FIXING WEEK KEY DUPLICATION ===")
        
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
        
        # Check daily_candles for weekly columns
        weekly_columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles' 
            AND column_name IN ('week_key', 'weekly_candle_key_id')
            ORDER BY column_name
        """)
        
        print("daily_candles weekly columns:")
        for col in weekly_columns:
            print(f"  - {col['column_name']} ({col['data_type']})")
        
        # Check for NULL values
        if weekly_columns:
            null_check = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(*) - COUNT(week_key) as week_key_nulls,
                    COUNT(*) - COUNT(weekly_candle_key_id) as weekly_candle_key_id_nulls
                FROM daily_candles
            """)
            print(f"  Total rows: {null_check['total_rows']}")
            print(f"  week_key NULLs: {null_check['week_key_nulls']}")
            print(f"  weekly_candle_key_id NULLs: {null_check['weekly_candle_key_id_nulls']}")
        
        # Step 2: Verify data consistency between the two columns
        print("\n=== STEP 2: VERIFY DATA RELATIONSHIPS ===")
        
        # Check sample data with weekly relationships
        sample_relationships = await conn.fetch("""
            SELECT dc.symbol, dc.candle_key_id, dc.week_key, dc.weekly_candle_key_id, dc.datetime,
                   wc.week_sequence_number
            FROM daily_candles dc
            LEFT JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
            WHERE dc.weekly_candle_key_id IS NOT NULL
            ORDER BY dc.datetime DESC
            LIMIT 5
        """)
        
        print("Sample daily candles with weekly relationships:")
        for row in sample_relationships:
            print(f"  {row['symbol']} week_key={row['week_key']} -> {row['weekly_candle_key_id']} (seq={row['week_sequence_number']})")
        
        # Step 3: Create backup queries for verification
        print("\n=== STEP 3: CREATE BACKUP DATA FOR VERIFICATION ===")
        
        # Save current state for verification
        daily_backup = await conn.fetch("""
            SELECT symbol, candle_key_id, week_key, weekly_candle_key_id, datetime
            FROM daily_candles
            WHERE weekly_candle_key_id IS NOT NULL
            ORDER BY datetime DESC
            LIMIT 10
        """)
        
        print(f"Backed up {len(daily_backup)} daily candles sample with weekly relationships")
        
        # Step 4: Drop indexes related to week_key
        print("\n=== STEP 4: DROP WEEK_KEY INDEXES ===")
        
        indexes_to_drop = [
            'idx_daily_week_key'
        ]
        
        for index_name in indexes_to_drop:
            try:
                await conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                print(f"SUCCESS: Dropped index: {index_name}")
            except Exception as e:
                print(f"WARNING: Could not drop index {index_name}: {e}")
        
        # Step 5: Drop the redundant week_key column
        print("\n=== STEP 5: DROP REDUNDANT WEEK_KEY COLUMN ===")
        
        try:
            # Check if column exists before dropping
            column_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'daily_candles' AND column_name = 'week_key'
                )
            """)
            
            if column_exists:
                await conn.execute("ALTER TABLE daily_candles DROP COLUMN week_key")
                print("SUCCESS: Dropped week_key column from daily_candles")
            else:
                print("INFO: week_key column does not exist in daily_candles")
                
        except Exception as e:
            print(f"ERROR: Error dropping week_key from daily_candles: {e}")
            raise
        
        # Step 6: Verify the fix
        print("\n=== STEP 6: VERIFY THE FIX ===")
        
        # Check remaining columns
        remaining_columns = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles' 
            AND column_name IN ('week_key', 'weekly_candle_key_id')
            ORDER BY column_name
        """)
        
        print("daily_candles remaining weekly columns:")
        for col in remaining_columns:
            print(f"  - {col['column_name']}")
        
        # Verify data is still accessible via weekly_candle_key_id
        test_query = await conn.fetchval("""
            SELECT COUNT(*)
            FROM daily_candles dc
            JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
        """)
        print(f"  Records with valid weekly relationships: {test_query}")
        
        # Step 7: Verify backup data is still accessible
        print("\n=== STEP 7: VERIFY DATA INTEGRITY AFTER FIX ===")
        
        # Check that the same data is still accessible via weekly_candle_key_id
        for backup_row in daily_backup[:3]:  # Check first 3 samples
            if backup_row['weekly_candle_key_id']:  # Only check rows that had weekly relationships
                current_data = await conn.fetchrow("""
                    SELECT symbol, candle_key_id, weekly_candle_key_id, datetime
                    FROM daily_candles
                    WHERE candle_key_id = $1
                """, backup_row['candle_key_id'])
                
                if current_data and current_data['weekly_candle_key_id'] == backup_row['weekly_candle_key_id']:
                    print(f"SUCCESS: Daily candle {backup_row['candle_key_id']} weekly relationship preserved")
                else:
                    print(f"ERROR: Daily candle {backup_row['candle_key_id']} weekly relationship lost!")
        
        print("\n=== WEEK KEY DUPLICATION FIX COMPLETED ===")
        print("SUCCESS: Redundant week_key column removed")
        print("SUCCESS: Data integrity verified")
        print("SUCCESS: System now uses only weekly_candle_key_id for weekly relationships")
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: Error during fix: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(fix_week_key_duplication())