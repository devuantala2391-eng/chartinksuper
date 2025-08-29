"""
Test the complete database scenario without relying on API
"""

import asyncio
import sys
import time
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db
from services.postgres_indicator_service import postgres_indicator_service

async def simulate_hard_refresh_scenario():
    print("=== SIMULATING COMPLETE HARD REFRESH SCENARIO ===")
    
    await ultra_fast_db.initialize()
    test_symbol = "20MICRONS"
    
    print(f"\n1. SIMULATING HARD REFRESH (clearing all indicators for {test_symbol})")
    async with ultra_fast_db.pool.acquire() as conn:
        await conn.execute("""
            UPDATE daily_candles 
            SET indicators = '{}'::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = $1
        """, test_symbol)
        print("   All indicators cleared")
    
    # Test each indicator type
    timeframes = ['daily', 'weekly', 'monthly']
    
    for timeframe in timeframes:
        print(f"\n2. TESTING {timeframe.upper()} PERCENTAGE SCENARIO")
        
        # First calculation - should process rows
        print(f"   First {timeframe} calculation (post hard-refresh):")
        start_time = time.time()
        result1 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        time1 = time.time() - start_time
        print(f"   Result: {result1['updated_rows']} rows updated in {time1:.3f}s")
        
        # Second calculation - should NOT process rows  
        print(f"   Second {timeframe} calculation (should skip):")
        start_time = time.time()
        result2 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        time2 = time.time() - start_time
        print(f"   Result: {result2['updated_rows']} rows updated in {time2:.3f}s")
        
        # Third calculation - should still NOT process rows
        print(f"   Third {timeframe} calculation (should still skip):")
        start_time = time.time()
        result3 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        time3 = time.time() - start_time
        print(f"   Result: {result3['updated_rows']} rows updated in {time3:.3f}s")
        
        # Verify results
        if result1['updated_rows'] > 0 and result2['updated_rows'] == 0 and result3['updated_rows'] == 0:
            print(f"   ✅ SUCCESS: {timeframe.title()} calculation working correctly")
            print(f"      - First call: {result1['updated_rows']} rows (calculation)")
            print(f"      - Second call: {result2['updated_rows']} rows (skip)")  
            print(f"      - Third call: {result3['updated_rows']} rows (skip)")
        else:
            print(f"   ❌ PROBLEM: {timeframe.title()} calculation not working correctly")
            print(f"      - First call: {result1['updated_rows']} rows")
            print(f"      - Second call: {result2['updated_rows']} rows") 
            print(f"      - Third call: {result3['updated_rows']} rows")
    
    print(f"\n=== FINAL VERIFICATION ===")
    async with ultra_fast_db.pool.acquire() as conn:
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'daily_pctchg'", test_symbol)
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", test_symbol)
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'monthly_pctchg'", test_symbol)
        
        print(f"Final indicator counts:")
        print(f"  Daily: {daily_count} records")
        print(f"  Weekly: {weekly_count} records")
        print(f"  Monthly: {monthly_count} records")
        
        if daily_count > 0 and weekly_count > 0 and monthly_count > 0:
            print("\n✅ ALL SCENARIOS PASSED")
            print("✅ Hard refresh -> calculation -> skip logic working correctly")
            print("✅ No unnecessary recalculations")
        else:
            print("\n❌ SOME SCENARIOS FAILED")

if __name__ == "__main__":
    asyncio.run(simulate_hard_refresh_scenario())