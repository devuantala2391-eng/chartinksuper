import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def check_monthly_results():
    await ultra_fast_db.initialize()
    async with ultra_fast_db.pool.acquire() as conn:
        # Get recent records with monthly percentage
        records = await conn.fetch("""
            SELECT 
                datetime, 
                close, 
                indicators->'monthly_pctchg' as monthly_pct, 
                monthly_candle_key_id
            FROM daily_candles 
            WHERE symbol = $1 
              AND indicators ? 'monthly_pctchg'
            ORDER BY datetime DESC 
            LIMIT 15
        """, "20MICRONS")
        
        print("Recent records with monthly percentage:")
        for r in records:
            print(f"  {r['datetime']}: close={r['close']:.2f}, monthly%={r['monthly_pct']}, month={r['monthly_candle_key_id']}")
        
        # Check for different percentages within the same month
        if records:
            current_month = records[0]['monthly_candle_key_id']
            same_month = [r for r in records if r['monthly_candle_key_id'] == current_month]
            if len(same_month) > 1:
                print(f"\nDays in current month {current_month}:")
                percentages = []
                for r in same_month:
                    print(f"  {r['datetime']}: {r['monthly_pct']}%")
                    if r['monthly_pct']:
                        percentages.append(float(r['monthly_pct']))
                
                if len(set(percentages)) > 1:
                    print("✅ SUCCESS: Different percentages within same month - dynamic sliding window working!")
                else:
                    print("❌ PROBLEM: All days have same percentage")

asyncio.run(check_monthly_results())