"""
Debug which row is being updated on the second daily calculation
"""

import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def debug_daily_issue():
    await ultra_fast_db.initialize()
    test_symbol = "20MICRONS"
    
    async with ultra_fast_db.pool.acquire() as conn:
        # Check if there are any rows without daily_pctchg after first calculation
        missing_daily = await conn.fetch("""
            SELECT candle_key_id, datetime, close, indicators
            FROM daily_candles 
            WHERE symbol = $1 
              AND (
                  NOT (indicators ? 'daily_pctchg') OR 
                  (indicators->'daily_pctchg') IS NULL OR
                  (indicators->'daily_pctchg') = 'null'::jsonb
              )
            ORDER BY datetime DESC
            LIMIT 5
        """, test_symbol)
        
        print(f"Rows missing daily_pctchg: {len(missing_daily)}")
        for row in missing_daily:
            print(f"  {row['datetime']}: {row['candle_key_id']} - indicators: {row['indicators']}")
        
        # Check if there are any rows with null daily_pctchg values
        null_daily = await conn.fetch("""
            SELECT candle_key_id, datetime, close, indicators->'daily_pctchg' as daily_pct
            FROM daily_candles 
            WHERE symbol = $1 
              AND indicators ? 'daily_pctchg'
              AND (indicators->'daily_pctchg') IS NULL
            LIMIT 5
        """, test_symbol)
        
        print(f"Rows with null daily_pctchg: {len(null_daily)}")
        for row in null_daily:
            print(f"  {row['datetime']}: {row['candle_key_id']} - daily_pct: {row['daily_pct']}")

asyncio.run(debug_daily_issue())