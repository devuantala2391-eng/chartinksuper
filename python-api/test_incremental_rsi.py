#!/usr/bin/env python3
"""
Test if incremental RSI calculation works after state is populated
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_incremental_rsi():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        symbol = 'RELIANCE'
        print(f'=== TESTING INCREMENTAL RSI FOR {symbol} ===')
        print()

        # Check current state
        before = await conn.fetchrow('''
            SELECT indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 1
        ''', symbol)

        if before and before['indicators']:
            indicators = json.loads(before['indicators'])
            print('BEFORE second run:')
            print(f'  RSI value: {indicators.get("daily_rsi_14", "NOT FOUND")}')
            print(f'  Avg gain state: {indicators.get("_daily_rsi_14_avg_gain", "NOT FOUND")}')
            print(f'  Avg loss state: {indicators.get("_daily_rsi_14_avg_loss", "NOT FOUND")}')
        print()

        # Run the cron function again - this time it should use incremental calculation
        print('Running cron function second time (should be incremental)...')
        result = await conn.fetchrow('''
            SELECT * FROM cron_calculate_rsi_for_symbol($1, 'daily', 14)
        ''', symbol)

        print(f'Result:')
        print(f'  Status: {result["status"]} <- Should be SUCCESS, not FALLBACK!')
        print(f'  Updated rows: {result["updated_rows"]}')
        print(f'  RSI value: {result["rsi_value"]}')
        print(f'  Warning: {result["warning_message"]}')
        print(f'  Execution time: {result["execution_time_ms"]}ms')
        print()

        if result["status"] == "SUCCESS":
            print('🎉 SUCCESS: Incremental calculation is working!')
        else:
            print('⚠️  Still using fallback - needs investigation')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_incremental_rsi())