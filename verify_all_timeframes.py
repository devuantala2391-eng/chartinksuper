import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def verify():
    await ultra_fast_db.initialize()
    async with ultra_fast_db.pool.acquire() as conn:
        # Check all timeframes
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'daily_pctchg'", "20MICRONS")
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", "20MICRONS")
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'monthly_pctchg'", "20MICRONS")
        
        print(f"Daily percentages: {daily_count} records")
        print(f"Weekly percentages: {weekly_count} records")  
        print(f"Monthly percentages: {monthly_count} records")

asyncio.run(verify())