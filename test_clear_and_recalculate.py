"""
Clear existing weekly percentages and recalculate to test dynamic sliding window
"""

import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def clear_and_recalculate():
    print("=== CLEARING AND RECALCULATING WEEKLY PERCENTAGES ===")
    
    await ultra_fast_db.initialize()
    
    async with ultra_fast_db.pool.acquire() as conn:
        # Clear existing weekly percentages for 20MICRONS
        print("Clearing existing weekly percentages...")
        await conn.execute("""
            UPDATE daily_candles 
            SET indicators = indicators - 'weekly_pctchg',
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = $1 AND indicators ? 'weekly_pctchg'
        """, "20MICRONS")
        
        # Verify cleared
        count_after_clear = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", 
            "20MICRONS"
        )
        print(f"Records with weekly percentage after clearing: {count_after_clear}")
        
        # Now recalculate using the stored procedure
        print("\nRecalculating weekly percentages...")
        result = await conn.fetchrow(
            "SELECT * FROM calculate_weekly_percentage_change_for_symbol($1)",
            "20MICRONS"
        )
        print(f"Calculation result: {dict(result)}")
        
        # Check results
        count_after_calc = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", 
            "20MICRONS"
        )
        print(f"Records with weekly percentage after recalculation: {count_after_calc}")
        
        if count_after_calc > 0:
            # Get records from the same week to see if they have different percentages
            print("\n=== CHECKING DYNAMIC SLIDING WINDOW ===")
            sample_week = await conn.fetch("""
                SELECT 
                    datetime, 
                    close, 
                    indicators->'weekly_pctchg' as weekly_pct, 
                    weekly_candle_key_id
                FROM daily_candles 
                WHERE symbol = $1 
                  AND indicators ? 'weekly_pctchg'
                  AND weekly_candle_key_id = (
                      SELECT weekly_candle_key_id 
                      FROM daily_candles 
                      WHERE symbol = $1 AND indicators ? 'weekly_pctchg'
                      ORDER BY datetime DESC 
                      LIMIT 1
                  )
                ORDER BY datetime
            """, "20MICRONS", "20MICRONS")
            
            print(f"Days in the most recent week ({sample_week[0]['weekly_candle_key_id']} if available):")
            for record in sample_week:
                print(f"  {record['datetime']}: close={record['close']:.2f}, weekly%={record['weekly_pct']}%")
            
            # Show if percentages are different
            percentages = [float(r['weekly_pct']) for r in sample_week]
            unique_percentages = set(percentages)
            
            if len(unique_percentages) > 1:
                print("✅ SUCCESS: Different percentages within same week - dynamic sliding window working!")
            else:
                print("❌ PROBLEM: All days in the same week have identical percentages")

if __name__ == "__main__":
    asyncio.run(clear_and_recalculate())