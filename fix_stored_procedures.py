"""
Fix the stored procedures to ensure they work without week_key column
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_stored_procedures():
    """Fix stored procedures to work without week_key"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("=== FIXING STORED PROCEDURES ===")
        
        # Drop existing stored procedures to clear any cached plans
        procedures_to_drop = [
            'process_symbol_weekly_only',
            'process_all_symbols_weekly_only',
            'generate_weekly_candles_for_symbol',
            'process_symbol_comprehensive',
            'process_all_symbols_comprehensive',
            'calculate_week_key'
        ]
        
        for proc in procedures_to_drop:
            try:
                await conn.execute(f"DROP FUNCTION IF EXISTS {proc}() CASCADE")
                print(f"Dropped function: {proc}")
            except Exception as e:
                print(f"Could not drop {proc}: {e}")
        
        # Reload the stored procedures file to recreate them with the updated SQL
        print("\nReloading stored procedures from file...")
        
        with open('python-api/sql/stored_procedures/comprehensive_calculations.sql', 'r') as f:
            sql_content = f.read()
        
        # Execute the SQL file to recreate all procedures
        await conn.execute(sql_content)
        print("SUCCESS: Stored procedures recreated")
        
        # Test one of the procedures to make sure it works
        print("\nTesting stored procedures...")
        
        # Check if we have daily candles to test with
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        print(f"Daily candles available: {daily_count}")
        
        if daily_count > 0:
            # Test the weekly generation for 20MICRONS
            result = await conn.fetchrow("SELECT * FROM process_symbol_weekly_only('20MICRONS')")
            print(f"Test result: {dict(result)}")
        else:
            print("No daily candles to test with")
        
        await conn.close()
        print("SUCCESS: Stored procedures fix completed")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(fix_stored_procedures())
    if success:
        print("\nStored procedures fix: SUCCESS")
    else:
        print("\nStored procedures fix: FAILED")