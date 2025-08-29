"""
Test volume indicators with dynamic sliding window approach
"""

import asyncio
import sys
sys.path.append('python-api')
from services.postgres_indicator_service import postgres_indicator_service
from services.ultra_fast_database_service import ultra_fast_db

async def test_volume_indicators():
    print("=== TESTING VOLUME INDICATORS (DYNAMIC SLIDING WINDOW - CUMULATIVE TYPE) ===")
    
    await ultra_fast_db.initialize()
    test_symbol = "20MICRONS"
    
    # First, clear existing volume indicators to test from scratch
    print(f"\n1. Clearing existing volume indicators for {test_symbol}...")
    async with ultra_fast_db.pool.acquire() as conn:
        await conn.execute("""
            UPDATE daily_candles 
            SET indicators = indicators - 'weekly_volume' - 'monthly_volume',
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = $1
        """, test_symbol)
        
        print("   Volume indicators cleared")
    
    # Test Weekly Volume
    print(f"\n2. Testing WEEKLY VOLUME calculation...")
    result_weekly = await postgres_indicator_service.calculate_volume_for_symbol(
        symbol=test_symbol,
        timeframe='weekly'
    )
    print(f"   Weekly volume result: {result_weekly['updated_rows']} rows updated")
    print(f"   Status: {result_weekly['status']}")
    
    # Test Monthly Volume
    print(f"\n3. Testing MONTHLY VOLUME calculation...")
    result_monthly = await postgres_indicator_service.calculate_volume_for_symbol(
        symbol=test_symbol,
        timeframe='monthly'
    )
    print(f"   Monthly volume result: {result_monthly['updated_rows']} rows updated")
    print(f"   Status: {result_monthly['status']}")
    
    # Verify the results
    if result_weekly['success'] and result_monthly['success']:
        print(f"\n4. VERIFYING DYNAMIC SLIDING WINDOW BEHAVIOR...")
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Get records from the same week to verify sliding window
            same_week_records = await conn.fetch("""
                SELECT 
                    datetime,
                    volume as daily_volume,
                    indicators->'weekly_volume' as weekly_volume,
                    indicators->'monthly_volume' as monthly_volume,
                    weekly_candle_key_id
                FROM daily_candles 
                WHERE symbol = $1 
                  AND indicators ? 'weekly_volume'
                  AND indicators ? 'monthly_volume'
                  AND weekly_candle_key_id IN (
                      SELECT weekly_candle_key_id 
                      FROM daily_candles 
                      WHERE symbol = $2
                        AND indicators ? 'weekly_volume'
                      GROUP BY weekly_candle_key_id 
                      HAVING COUNT(*) > 1
                      LIMIT 1
                  )
                ORDER BY datetime
            """, test_symbol, test_symbol)
            
            if same_week_records and len(same_week_records) > 1:
                print(f"\n   Found {len(same_week_records)} days in the same week:")
                print("   Date        | Daily Vol | Weekly Vol | Monthly Vol | Week Key")
                print("   " + "-" * 70)
                
                weekly_volumes = []
                for record in same_week_records:
                    daily_vol = int(record['daily_volume'])
                    weekly_vol = int(record['weekly_volume']) if record['weekly_volume'] else None
                    monthly_vol = int(record['monthly_volume']) if record['monthly_volume'] else None
                    weekly_volumes.append(weekly_vol)
                    
                    print(f"   {record['datetime']} | {daily_vol:,} | {weekly_vol:,} | {monthly_vol:,} | {record['weekly_candle_key_id']}")
                
                # Verify sliding window behavior
                if len(set(weekly_volumes)) > 1:
                    print("\n   ✅ SUCCESS: Different weekly volumes within same week")
                    print("   ✅ Dynamic sliding window working - each day shows cumulative volume")
                    
                    # Verify cumulative pattern
                    if all(weekly_volumes[i] <= weekly_volumes[i+1] for i in range(len(weekly_volumes)-1)):
                        print("   ✅ EXCELLENT: Weekly volumes increase progressively (cumulative pattern)")
                    else:
                        print("   ⚠️  WARNING: Weekly volumes not in progressive order")
                else:
                    print("   ❌ PROBLEM: All days have same weekly volume")
            else:
                print("   ⚠️  No multiple days found in same week to verify sliding window")
    
    # Test recalculation prevention
    print(f"\n5. TESTING RECALCULATION PREVENTION...")
    
    # Second weekly calculation - should update 0 rows
    result_weekly2 = await postgres_indicator_service.calculate_volume_for_symbol(
        symbol=test_symbol,
        timeframe='weekly'
    )
    print(f"   Second weekly calculation: {result_weekly2['updated_rows']} rows updated")
    
    # Second monthly calculation - should update 0 rows
    result_monthly2 = await postgres_indicator_service.calculate_volume_for_symbol(
        symbol=test_symbol,
        timeframe='monthly'
    )
    print(f"   Second monthly calculation: {result_monthly2['updated_rows']} rows updated")
    
    if result_weekly2['updated_rows'] == 0 and result_monthly2['updated_rows'] == 0:
        print("   ✅ SUCCESS: Recalculation prevention working correctly")
    else:
        print("   ❌ PROBLEM: Indicators being recalculated unnecessarily")
    
    print(f"\n=== VOLUME INDICATORS TEST SUMMARY ===")
    print(f"Weekly Volume: First={result_weekly['updated_rows']}, Second={result_weekly2['updated_rows']}")
    print(f"Monthly Volume: First={result_monthly['updated_rows']}, Second={result_monthly2['updated_rows']}")

if __name__ == "__main__":
    asyncio.run(test_volume_indicators())