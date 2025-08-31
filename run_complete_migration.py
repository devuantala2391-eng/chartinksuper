"""
Run complete migration to apply prefixed indicators to all symbols
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def run_complete_migration():
    """Run complete migration to apply prefixes to all indicators"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("\n" + "="*60)
        print("COMPLETE INDICATOR MIGRATION TO PREFIXED FORMAT")
        print("="*60)
        print(f"Started at: {datetime.now()}")
        
        # Step 1: Remove old format indicators from ALL symbols
        print("\n[STEP 1] Removing old format indicators from all symbols...")
        result = await conn.fetchrow("""
            SELECT * FROM remove_old_format_indicators(NULL)
        """)
        print(f"  - Symbols processed: {result['symbols_processed']}")
        print(f"  - Rows updated: {result['rows_updated']}")
        print(f"  - Status: {result['status']}")
        
        # Step 2: Calculate daily percentage change for all symbols
        print("\n[STEP 2] Calculating daily percentage change...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_timeframe_percentage_change('daily', NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        
        # Step 3: Calculate weekly percentage change for all symbols
        print("\n[STEP 3] Calculating weekly percentage change...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_timeframe_percentage_change('weekly', NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        
        # Step 4: Calculate monthly percentage change for all symbols
        print("\n[STEP 4] Calculating monthly percentage change...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_timeframe_percentage_change('monthly', NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        
        # Step 5: Calculate daily SuperTrend(10,3) for all symbols
        print("\n[STEP 5] Calculating daily SuperTrend(10,3)...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_timeframe_supertrend('daily', 10, 3.0, NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        print(f"  - Indicator key: {result['indicator_key']}")
        print(f"  - Direction key: {result['direction_key']}")
        
        # Step 6: Calculate weekly SuperTrend(10,3) for all symbols
        print("\n[STEP 6] Calculating weekly SuperTrend(10,3)...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_weekly_monthly_supertrend('weekly', 10, 3.0, NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Symbols processed: {result['processed_symbols']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        print(f"  - Indicator key: {result['indicator_key']}")
        print(f"  - Direction key: {result['direction_key']}")
        
        # Step 7: Calculate monthly SuperTrend(10,3) for all symbols
        print("\n[STEP 7] Calculating monthly SuperTrend(10,3)...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_weekly_monthly_supertrend('monthly', 10, 3.0, NULL)
        """)
        print(f"  - Status: {result['status']}")
        print(f"  - Symbols processed: {result['processed_symbols']}")
        print(f"  - Rows updated: {result['updated_rows']}")
        print(f"  - Indicator key: {result['indicator_key']}")
        print(f"  - Direction key: {result['direction_key']}")
        
        # Verification: Check a sample symbol
        print("\n[VERIFICATION] Checking sample symbol (20MICRONS)...")
        result = await conn.fetch("""
            SELECT * FROM verify_indicator_migration('20MICRONS')
        """)
        
        old_count = 0
        new_daily = 0
        new_weekly = 0
        new_monthly = 0
        
        for row in result:
            if row['format_type'] == 'OLD - No Prefix':
                old_count += 1
            elif row['format_type'] == 'NEW - Daily':
                new_daily += 1
            elif row['format_type'] == 'NEW - Weekly':
                new_weekly += 1
            elif row['format_type'] == 'NEW - Monthly':
                new_monthly += 1
        
        print(f"  - OLD format indicators: {old_count}")
        print(f"  - NEW Daily indicators: {new_daily}")
        print(f"  - NEW Weekly indicators: {new_weekly}")
        print(f"  - NEW Monthly indicators: {new_monthly}")
        
        if old_count == 0:
            print("\n[SUCCESS] Migration completed successfully!")
            print("All indicators now have proper timeframe prefixes.")
        else:
            print(f"\n[WARNING] Found {old_count} indicators still in old format.")
            print("Please check the logs for issues.")
        
        print(f"\nCompleted at: {datetime.now()}")
        print("="*60)
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(run_complete_migration())