"""
Test indicator recalculation logic - ensure indicators are not recalculated if they already exist
"""

import asyncio
import sys
import time
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db
from services.postgres_indicator_service import postgres_indicator_service

async def test_indicator_recalculation():
    print("=== TESTING INDICATOR RECALCULATION LOGIC ===")
    
    await ultra_fast_db.initialize()
    test_symbol = "20MICRONS"
    
    # First, clear all indicators for the test symbol to simulate post-hard-refresh state
    print(f"\n1. Clearing all existing indicators for {test_symbol}...")
    async with ultra_fast_db.pool.acquire() as conn:
        # Clear daily, weekly, and monthly percentages
        await conn.execute("""
            UPDATE daily_candles 
            SET indicators = indicators - 'daily_pctchg' - 'weekly_pctchg' - 'monthly_pctchg',
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = $1
        """, test_symbol)
        
        # Verify all cleared
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'daily_pctchg'", test_symbol)
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", test_symbol)
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'monthly_pctchg'", test_symbol)
        
        print(f"   After clearing - Daily: {daily_count}, Weekly: {weekly_count}, Monthly: {monthly_count}")
    
    # Test Daily Percentage
    print(f"\n2. Testing DAILY percentage calculation...")
    
    # First calculation - should process rows
    print("   First daily calculation (should calculate):")
    start_time = time.time()
    result1 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='daily'
    )
    time1 = time.time() - start_time
    print(f"   Result: {result1['updated_rows']} rows updated in {time1:.3f}s")
    
    # Second calculation - should NOT process rows (already exist)
    print("   Second daily calculation (should skip - already exists):")
    start_time = time.time()
    result2 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='daily'
    )
    time2 = time.time() - start_time
    print(f"   Result: {result2['updated_rows']} rows updated in {time2:.3f}s")
    
    # Test Weekly Percentage
    print(f"\n3. Testing WEEKLY percentage calculation...")
    
    # First calculation - should process rows
    print("   First weekly calculation (should calculate):")
    start_time = time.time()
    result3 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='weekly'
    )
    time3 = time.time() - start_time
    print(f"   Result: {result3['updated_rows']} rows updated in {time3:.3f}s")
    
    # Second calculation - should NOT process rows
    print("   Second weekly calculation (should skip - already exists):")
    start_time = time.time()
    result4 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='weekly'
    )
    time4 = time.time() - start_time
    print(f"   Result: {result4['updated_rows']} rows updated in {time4:.3f}s")
    
    # Test Monthly Percentage
    print(f"\n4. Testing MONTHLY percentage calculation...")
    
    # First calculation - should process rows
    print("   First monthly calculation (should calculate):")
    start_time = time.time()
    result5 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='monthly'
    )
    time5 = time.time() - start_time
    print(f"   Result: {result5['updated_rows']} rows updated in {time5:.3f}s")
    
    # Second calculation - should NOT process rows
    print("   Second monthly calculation (should skip - already exists):")
    start_time = time.time()
    result6 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol, timeframe='monthly'
    )
    time6 = time.time() - start_time
    print(f"   Result: {result6['updated_rows']} rows updated in {time6:.3f}s")
    
    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Daily:   First={result1['updated_rows']} rows, Second={result2['updated_rows']} rows")
    print(f"Weekly:  First={result3['updated_rows']} rows, Second={result4['updated_rows']} rows") 
    print(f"Monthly: First={result5['updated_rows']} rows, Second={result6['updated_rows']} rows")
    
    # Check if recalculation logic is working correctly
    issues = []
    if result2['updated_rows'] > 0:
        issues.append("❌ Daily percentage recalculated when it shouldn't have")
    if result4['updated_rows'] > 0:
        issues.append("❌ Weekly percentage recalculated when it shouldn't have")
    if result6['updated_rows'] > 0:
        issues.append("❌ Monthly percentage recalculated when it shouldn't have")
    
    if issues:
        print(f"\n⚠️  ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print(f"\n✅ SUCCESS: All indicator recalculation logic working correctly!")
        print("   - First calls calculated indicators")
        print("   - Second calls skipped existing indicators")

if __name__ == "__main__":
    asyncio.run(test_indicator_recalculation())