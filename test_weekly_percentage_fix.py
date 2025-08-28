"""
Test the fixed weekly percentage calculation with dynamic sliding window approach
"""

import asyncio
import sys
sys.path.append('python-api')
from services.postgres_indicator_service import postgres_indicator_service
from services.ultra_fast_database_service import ultra_fast_db

async def test_weekly_percentage_fix():
    """Test that weekly percentage now uses dynamic sliding window approach"""
    
    print("=== TESTING WEEKLY PERCENTAGE DYNAMIC SLIDING WINDOW ===")
    
    await ultra_fast_db.initialize()
    
    # Test with a specific symbol to see the calculation
    test_symbol = "20MICRONS"
    
    print(f"\nTesting weekly percentage calculation for {test_symbol}...")
    
    # Calculate weekly percentage for the test symbol
    result = await postgres_indicator_service.calculate_percentage_change_for_symbol(
        symbol=test_symbol,
        timeframe='weekly'
    )
    
    print(f"Calculation result: {result}")
    
    if result['success']:
        print(f"SUCCESS: Updated {result['updated_rows']} rows")
        
        # Now let's verify the data by querying a few records
        async with ultra_fast_db.pool.acquire() as conn:
            # Get recent daily records with weekly percentage
            records = await conn.fetch("""
                SELECT 
                    date,
                    symbol,
                    close,
                    indicators->'weekly_pctchg' as weekly_pctchg,
                    weekly_candle_key_id
                FROM daily_candles 
                WHERE symbol = $1 
                  AND indicators ? 'weekly_pctchg'
                  AND indicators->'weekly_pctchg' IS NOT NULL
                ORDER BY date DESC 
                LIMIT 10
            """, test_symbol)
            
            if records:
                print(f"\nFound {len(records)} records with weekly percentage:")
                print("Date        | Close  | Weekly % | Weekly Key")
                print("-" * 50)
                for record in records:
                    weekly_pct = record['weekly_pctchg']
                    if weekly_pct and str(weekly_pct) != 'null':
                        print(f"{record['date']} | {record['close']:6.2f} | {weekly_pct:7.2f}% | {record['weekly_candle_key_id']}")
                
                # Check if different days in the same week have different percentages
                print("\n=== VERIFYING DYNAMIC SLIDING WINDOW ===")
                print("Checking if different days in same week have different weekly percentages...")
                
                # Group by weekly_candle_key_id to see if same week has different percentages
                same_week_records = await conn.fetch("""
                    SELECT 
                        date,
                        close,
                        indicators->'weekly_pctchg' as weekly_pctchg,
                        weekly_candle_key_id
                    FROM daily_candles 
                    WHERE symbol = $1 
                      AND indicators ? 'weekly_pctchg'
                      AND indicators->'weekly_pctchg' IS NOT NULL
                      AND weekly_candle_key_id IN (
                          SELECT weekly_candle_key_id 
                          FROM daily_candles 
                          WHERE symbol = $1 
                            AND indicators ? 'weekly_pctchg'
                          GROUP BY weekly_candle_key_id 
                          HAVING COUNT(*) > 1
                          LIMIT 1
                      )
                    ORDER BY date
                """, test_symbol)
                
                if same_week_records and len(same_week_records) > 1:
                    print(f"Found {len(same_week_records)} days in the same week:")
                    prev_pct = None
                    for record in same_week_records:
                        weekly_pct = float(record['weekly_pctchg']) if record['weekly_pctchg'] else None
                        print(f"  {record['date']}: close={record['close']:.2f}, weekly%={weekly_pct:.2f}%")
                        if prev_pct is not None and abs(weekly_pct - prev_pct) > 0.01:
                            print("  ✅ GOOD: Different percentages within same week (dynamic sliding window working)")
                        prev_pct = weekly_pct
                else:
                    print("  ⚠️  No multiple days found in same week to verify sliding window")
            else:
                print("No records found with weekly percentage")
    else:
        print(f"FAILED: {result['status']}")

if __name__ == "__main__":
    asyncio.run(test_weekly_percentage_fix())