import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def check():
    await ultra_fast_db.initialize()
    async with ultra_fast_db.pool.acquire() as conn:
        # Get recent records with weekly percentage
        records = await conn.fetch("""
            SELECT 
                datetime, 
                close, 
                indicators->'weekly_pctchg' as weekly_pct, 
                weekly_candle_key_id
            FROM daily_candles 
            WHERE symbol = $1 
              AND indicators ? 'weekly_pctchg'
            ORDER BY datetime DESC 
            LIMIT 10
        """, "20MICRONS")
        
        print("Recent records with weekly percentage:")
        for r in records:
            print(f"  {r['datetime']}: close={r['close']:.2f}, weekly%={r['weekly_pct']}, week={r['weekly_candle_key_id']}")

asyncio.run(check())