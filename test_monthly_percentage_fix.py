"""
Test the fixed monthly percentage calculation with dynamic sliding window approach
"""

import asyncio
import sys
sys.path.append('python-api')
from services.postgres_indicator_service import postgres_indicator_service
from services.ultra_fast_database_service import ultra_fast_db

async def test_monthly_percentage_fix():
    """Test that monthly percentage now uses dynamic sliding window approach"""
    
    print("=== TESTING MONTHLY PERCENTAGE DYNAMIC SLIDING WINDOW ===")
    
    await ultra_fast_db.initialize()
    
    # Test with a specific symbol
    test_symbol = "20MICRONS"
    
    print(f"\nTesting monthly percentage calculation for {test_symbol}...")
    
    # First, clear existing monthly percentages to test clean calculation
    async with ultra_fast_db.pool.acquire() as conn:
        print("Clearing existing monthly percentages...")
        await conn.execute("""
            UPDATE daily_candles 
            SET indicators = indicators - 'monthly_pctchg',
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = $1 AND indicators ? 'monthly_pctchg'
        """, test_symbol)
    
    # Calculate monthly percentage for the test symbol
    result = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol,
        timeframe='monthly'
    )
    
    print(f"Calculation result: {result}")
    
    if result['success']:
        print(f"SUCCESS: Updated {result['updated_rows']} rows")
        
        # Now let's verify the data by querying records from different months
        async with ultra_fast_db.pool.acquire() as conn:
            # Get recent daily records with monthly percentage
            records = await conn.fetch("""
                SELECT 
                    datetime,
                    close,
                    indicators->'monthly_pctchg' as monthly_pct,
                    monthly_candle_key_id
                FROM daily_candles 
                WHERE symbol = $1 
                  AND indicators ? 'monthly_pctchg'
                  AND indicators->'monthly_pctchg' IS NOT NULL
                ORDER BY datetime DESC 
                LIMIT 15
            """, test_symbol)
            
            if records:
                print(f"\nFound {len(records)} records with monthly percentage:")
                print("Date        | Close  | Monthly % | Month Key")
                print("-" * 55)
                for record in records:
                    monthly_pct = record['monthly_pctchg']
                    if monthly_pct and str(monthly_pct) != 'null':
                        print(f"{record['datetime']} | {record['close']:6.2f} | {monthly_pct:8.2f}% | {record['monthly_candle_key_id']}")
                
                # Check if different days in the same month have different percentages
                print("\n=== VERIFYING DYNAMIC SLIDING WINDOW ===")
                print("Checking if different days in same month have different monthly percentages...")
                
                # Group by monthly_candle_key_id to see if same month has different percentages
                same_month_records = await conn.fetch("""
                    SELECT 
                        datetime,
                        close,
                        indicators->'monthly_pctchg' as monthly_pct,
                        monthly_candle_key_id
                    FROM daily_candles 
                    WHERE symbol = $1 
                      AND indicators ? 'monthly_pctchg'
                      AND indicators->'monthly_pctchg' IS NOT NULL
                      AND monthly_candle_key_id IN (
                          SELECT monthly_candle_key_id 
                          FROM daily_candles 
                          WHERE symbol = $1 
                            AND indicators ? 'monthly_pctchg'
                          GROUP BY monthly_candle_key_id 
                          HAVING COUNT(*) > 1
                          LIMIT 1
                      )
                    ORDER BY datetime
                """, test_symbol)
                
                if same_month_records and len(same_month_records) > 1:
                    print(f"Found {len(same_month_records)} days in the same month:")
                    prev_pct = None
                    has_different_percentages = False
                    for record in same_month_records:
                        monthly_pct = float(record['monthly_pct']) if record['monthly_pct'] else None
                        print(f"  {record['datetime']}: close={record['close']:.2f}, monthly%={monthly_pct:.2f}%")
                        if prev_pct is not None and abs(monthly_pct - prev_pct) > 0.01:
                            has_different_percentages = True
                        prev_pct = monthly_pct
                    
                    if has_different_percentages:
                        print("  ✅ GOOD: Different percentages within same month (dynamic sliding window working)")
                    else:
                        print("  ❌ PROBLEM: All days in the same month have identical percentages")
                else:
                    print("  ⚠️  No multiple days found in same month to verify sliding window")
            else:
                print("No records found with monthly percentage")
    else:
        print(f"FAILED: {result['status']}")

if __name__ == "__main__":
    asyncio.run(test_monthly_percentage_fix())