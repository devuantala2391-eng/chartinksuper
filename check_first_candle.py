import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def check():
    await ultra_fast_db.initialize()
    async with ultra_fast_db.pool.acquire() as conn:
        # Get the first few candles for 20MICRONS
        first_candles = await conn.fetch("""
            SELECT candle_key_id, candle_sequence_number, datetime, close, 
                   indicators->'daily_pctchg' as daily_pct
            FROM daily_candles 
            WHERE symbol = $1 
            ORDER BY candle_sequence_number 
            LIMIT 3
        """, "20MICRONS")
        
        print("First 3 candles for 20MICRONS:")
        for c in first_candles:
            print(f"  Seq {c['candle_sequence_number']}: {c['datetime']} - daily_pct={c['daily_pct']}")

asyncio.run(check())