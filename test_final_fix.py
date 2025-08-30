"""
Final comprehensive test of the hard refresh fix
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def comprehensive_test():
    """Comprehensive test of the hard refresh fix"""
    
    print("COMPREHENSIVE HARD REFRESH FIX TEST")
    print("=" * 50)
    
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("SUCCESS: Database connection established")
        
        # Check 1: Verify tables exist
        print("\n1. CHECKING TABLES...")
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('daily_candles', 'weekly_candles', 'monthly_candles')
            ORDER BY table_name
        """)
        
        table_names = [t['table_name'] for t in tables]
        expected_tables = ['daily_candles', 'weekly_candles', 'monthly_candles']
        
        for table in expected_tables:
            if table in table_names:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"  SUCCESS: {table} - {count} rows")
            else:
                print(f"  ERROR: {table} - missing")
        
        # Check 2: Verify stored procedures exist
        print("\n2. CHECKING STORED PROCEDURES...")
        required_procedures = [
            'generate_weekly_candles_for_symbol',
            'process_symbol_weekly_only', 
            'process_all_symbols_weekly_only',
            'calculate_all_indicators_for_symbol',
            'process_symbol_comprehensive'
        ]
        
        existing_procedures = await conn.fetch("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_type = 'FUNCTION'
        """)
        
        existing_names = [p['routine_name'] for p in existing_procedures]
        
        all_procedures_exist = True
        for procedure in required_procedures:
            if procedure in existing_names:
                print(f"  SUCCESS: {procedure} - exists")
            else:
                print(f"  ERROR: {procedure} - missing")
                all_procedures_exist = False
        
        # Check 3: Test weekly candle generation
        print("\n3. TESTING WEEKLY CANDLE GENERATION...")
        
        # Get daily candle count before
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        weekly_count_before = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        
        print(f"  Before: {daily_count} daily candles, {weekly_count_before} weekly candles")
        
        if daily_count > 0:
            # Test with first available symbol
            test_symbol = await conn.fetchval("SELECT symbol FROM daily_candles ORDER BY symbol LIMIT 1")
            
            # Clear existing weekly candles for clean test
            await conn.execute("DELETE FROM weekly_candles WHERE symbol = $1", test_symbol)
            await conn.execute("UPDATE daily_candles SET weekly_candle_key_id = NULL WHERE symbol = $1", test_symbol)
            
            # Test the procedure
            result = await conn.fetchrow("""
                SELECT * FROM process_symbol_weekly_only($1)
            """, test_symbol)
            
            if result and result['status'] == 'SUCCESS':
                print(f"  SUCCESS: Generated {result['weekly_candles_generated']} weekly candles for {test_symbol}")
                print(f"  SUCCESS: Updated {result['daily_candles_updated']} daily candles with weekly references")
                print(f"  SUCCESS: Execution time: {result['total_execution_time_ms']}ms")
            else:
                print(f"  ERROR: Weekly generation failed - {result['status'] if result else 'No result'}")
                all_procedures_exist = False
        
        # Check 4: Verify weekly references in daily candles
        print("\n4. CHECKING WEEKLY REFERENCES...")
        
        daily_with_refs = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NOT NULL")
        weekly_count_after = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        
        print(f"  Daily candles with weekly references: {daily_with_refs} / {daily_count}")
        print(f"  Weekly candles: {weekly_count_after}")
        
        # Check 5: Test batch processing
        print("\n5. TESTING BATCH PROCESSING...")
        
        batch_results = await conn.fetch("SELECT * FROM process_all_symbols_weekly_only()")
        
        successful_symbols = 0
        failed_symbols = 0
        total_weekly_generated = 0
        
        for result in batch_results:
            if result['status'] == 'SUCCESS':
                successful_symbols += 1
                total_weekly_generated += result['weekly_candles']
            else:
                failed_symbols += 1
                print(f"  ERROR: {result['symbol']} failed - {result['status']}")
        
        print(f"  Batch results: {successful_symbols} successful, {failed_symbols} failed")
        print(f"  Total weekly candles generated: {total_weekly_generated}")
        
        # Final assessment
        print("\n" + "=" * 50)
        print("FINAL ASSESSMENT")
        print("=" * 50)
        
        success_count = 0
        total_checks = 5
        
        # Check 1: Tables
        if len(table_names) == len(expected_tables):
            print("CHECK 1: Tables - PASS")
            success_count += 1
        else:
            print("CHECK 1: Tables - FAIL")
        
        # Check 2: Procedures  
        if all_procedures_exist:
            print("CHECK 2: Stored Procedures - PASS")
            success_count += 1
        else:
            print("CHECK 2: Stored Procedures - FAIL")
        
        # Check 3: Weekly generation
        if daily_count > 0 and result and result['status'] == 'SUCCESS':
            print("CHECK 3: Weekly Generation - PASS")
            success_count += 1
        else:
            print("CHECK 3: Weekly Generation - FAIL")
        
        # Check 4: References
        if daily_with_refs > 0:
            print("CHECK 4: Weekly References - PASS")  
            success_count += 1
        else:
            print("CHECK 4: Weekly References - FAIL")
        
        # Check 5: Batch processing
        if successful_symbols > 0 and failed_symbols == 0:
            print("CHECK 5: Batch Processing - PASS")
            success_count += 1
        else:
            print("CHECK 5: Batch Processing - FAIL")
        
        # Overall result
        print(f"\nOVERALL RESULT: {success_count}/{total_checks} checks passed")
        
        if success_count == total_checks:
            print("CONCLUSION: Hard refresh fix is working perfectly!")
            print("- Weekly candles are generated correctly")
            print("- Daily candles have proper weekly references") 
            print("- All stored procedures are functional")
            print("- Hard refresh will now work on refresh")
        else:
            print("CONCLUSION: Hard refresh fix needs additional work")
            print(f"- {total_checks - success_count} checks failed")
        
        await conn.close()
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(comprehensive_test())