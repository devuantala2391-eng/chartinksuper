import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def check_volume_results():
    await ultra_fast_db.initialize()
    async with ultra_fast_db.pool.acquire() as conn:
        # Get recent records with volume indicators
        records = await conn.fetch("""
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
            ORDER BY datetime DESC 
            LIMIT 10
        """, "20MICRONS")
        
        print("Recent records with volume indicators:")
        print("Date        | Daily Vol | Weekly Vol | Monthly Vol | Week Key")
        print("-" * 75)
        for r in records:
            daily_vol = int(r['daily_volume'])
            weekly_vol = int(r['weekly_volume']) if r['weekly_volume'] else 0
            monthly_vol = int(r['monthly_volume']) if r['monthly_volume'] else 0
            print(f"{r['datetime']} | {daily_vol:,} | {weekly_vol:,} | {monthly_vol:,} | {r['weekly_candle_key_id']}")
        
        # Check same week for sliding window
        if records:
            current_week = records[0]['weekly_candle_key_id']
            same_week = [r for r in records if r['weekly_candle_key_id'] == current_week]
            
            if len(same_week) > 1:
                print(f"\nDays in current week {current_week}:")
                weekly_volumes = []
                for r in same_week:
                    weekly_vol = int(r['weekly_volume']) if r['weekly_volume'] else 0
                    weekly_volumes.append(weekly_vol)
                    print(f"  {r['datetime']}: weekly_vol={weekly_vol:,}")
                
                if len(set(weekly_volumes)) > 1:
                    print("SUCCESS: Different weekly volumes - sliding window working!")
                else:
                    print("PROBLEM: All days have same weekly volume")

asyncio.run(check_volume_results())