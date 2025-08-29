import asyncio
import sys
import time
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db
from services.postgres_indicator_service import postgres_indicator_service

async def test():
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
    results = {}
    
    for timeframe in timeframes:
        print(f"\n2. TESTING {timeframe.upper()} PERCENTAGE SCENARIO")
        
        # First calculation
        result1 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        print(f"   First call: {result1['updated_rows']} rows updated")
        
        # Second calculation
        result2 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        print(f"   Second call: {result2['updated_rows']} rows updated")
        
        # Third calculation
        result3 = await postgres_indicator_service.calculate_percentage_change_for_symbol(
            symbol=test_symbol, timeframe=timeframe
        )
        print(f"   Third call: {result3['updated_rows']} rows updated")
        
        results[timeframe] = (result1['updated_rows'], result2['updated_rows'], result3['updated_rows'])
        
        if result1['updated_rows'] > 0 and result2['updated_rows'] == 0 and result3['updated_rows'] == 0:
            print(f"   SUCCESS: {timeframe.title()} working correctly")
        else:
            print(f"   PROBLEM: {timeframe.title()} not working correctly")
    
    print(f"\n=== RESULTS SUMMARY ===")
    for timeframe, (first, second, third) in results.items():
        print(f"{timeframe.title()}: First={first}, Second={second}, Third={third}")
    
    # Final verification
    async with ultra_fast_db.pool.acquire() as conn:
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'daily_pctchg'", test_symbol)
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", test_symbol)
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'monthly_pctchg'", test_symbol)
        
        print(f"\n=== FINAL VERIFICATION ===")
        print(f"Daily: {daily_count} records")
        print(f"Weekly: {weekly_count} records")
        print(f"Monthly: {monthly_count} records")

asyncio.run(test())