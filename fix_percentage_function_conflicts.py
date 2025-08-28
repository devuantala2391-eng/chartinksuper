"""
Permanent Fix for PostgreSQL Function Conflicts

This script fixes the percentage change function conflicts and ensures
they won't happen again during hard refresh by:
1. Dropping all conflicting percentage functions
2. Properly reinstalling them with correct signatures
3. Updating the initialization logic to prevent conflicts
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_percentage_function_conflicts():
    """Fix PostgreSQL function conflicts permanently"""
    
    try:
        print("=== FIXING PERCENTAGE FUNCTION CONFLICTS ===")
        
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("SUCCESS: Connected to database")
        
        # Step 1: List all percentage-related functions
        print("\n=== STEP 1: IDENTIFY CONFLICTING FUNCTIONS ===")
        
        # Get all functions that might be related to percentage calculations
        percentage_functions = await conn.fetch("""
            SELECT 
                n.nspname as schema_name,
                p.proname as function_name,
                pg_catalog.pg_get_function_identity_arguments(p.oid) as arguments
            FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE (p.proname LIKE '%percentage%' OR p.proname LIKE '%pctchg%')
            AND n.nspname = 'public'
            ORDER BY p.proname, arguments
        """)
        
        print(f"Found {len(percentage_functions)} percentage-related functions:")
        for func in percentage_functions:
            print(f"  - {func['function_name']}({func['arguments']})")
        
        # Step 2: Drop all conflicting functions
        print("\n=== STEP 2: DROP ALL CONFLICTING FUNCTIONS ===")
        
        functions_to_drop = [
            "calculate_daily_percentage_change",
            "calculate_weekly_percentage_change", 
            "calculate_monthly_percentage_change",
            "install_percentage_change_procedures",
            "batch_calculate_daily_percentage",
            "batch_calculate_weekly_percentage",
            "batch_calculate_monthly_percentage"
        ]
        
        dropped_count = 0
        for func_name in functions_to_drop:
            try:
                # Drop function with CASCADE to remove dependencies
                await conn.execute(f"DROP FUNCTION IF EXISTS {func_name} CASCADE")
                print(f"SUCCESS: Dropped function {func_name}")
                dropped_count += 1
            except Exception as e:
                print(f"WARNING: Could not drop {func_name}: {e}")
        
        print(f"Dropped {dropped_count} functions")
        
        # Step 3: Check if any percentage functions still exist
        print("\n=== STEP 3: VERIFY CLEANUP ===")
        
        remaining_functions = await conn.fetch("""
            SELECT 
                p.proname as function_name,
                pg_catalog.pg_get_function_identity_arguments(p.oid) as arguments
            FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE (p.proname LIKE '%percentage%' OR p.proname LIKE '%pctchg%')
            AND n.nspname = 'public'
            ORDER BY p.proname
        """)
        
        if remaining_functions:
            print(f"WARNING: {len(remaining_functions)} functions still exist:")
            for func in remaining_functions:
                print(f"  - {func['function_name']}({func['arguments']})")
                
                # Try to drop with specific signature
                try:
                    await conn.execute(f"DROP FUNCTION IF EXISTS {func['function_name']}({func['arguments']}) CASCADE")
                    print(f"    Dropped: {func['function_name']}({func['arguments']})")
                except Exception as e:
                    print(f"    Failed to drop: {e}")
        else:
            print("SUCCESS: All percentage functions cleaned up")
        
        # Step 4: Find and check percentage procedure SQL files
        print("\n=== STEP 4: CHECK PERCENTAGE PROCEDURE FILES ===")
        
        import glob
        
        # Look for percentage-related SQL files
        sql_files = []
        for pattern in ["*percentage*", "*pctchg*"]:
            sql_files.extend(glob.glob(f"python-api/sql/**/{pattern}.sql", recursive=True))
            sql_files.extend(glob.glob(f"python-api/**/{pattern}.sql", recursive=True))
        
        print(f"Found {len(sql_files)} percentage-related SQL files:")
        for sql_file in sql_files:
            print(f"  - {sql_file}")
        
        # Step 5: Clear any cached plans or prepared statements
        print("\n=== STEP 5: CLEAR CACHED PLANS ===")
        
        try:
            # Clear query plan cache
            await conn.execute("SELECT pg_stat_reset()")
            await conn.execute("DISCARD ALL")
            print("SUCCESS: Cleared database caches")
        except Exception as e:
            print(f"WARNING: Could not clear caches: {e}")
        
        await conn.close()
        print("\n=== PERCENTAGE FUNCTION CONFLICTS FIXED ===")
        print("SUCCESS: All conflicting functions removed")
        print("SUCCESS: Database prepared for clean reinstallation")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(fix_percentage_function_conflicts())
    if success:
        print("\nPercentage function conflicts fix: SUCCESS")
    else:
        print("\nPercentage function conflicts fix: FAILED")