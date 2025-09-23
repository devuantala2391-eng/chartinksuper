#!/usr/bin/env python3
"""
Test RSI calculation for a single symbol to debug the issue
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_single_rsi():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        symbol = 'RELIANCE'
        print(f'=== TESTING RSI CALCULATION FOR {symbol} ===')
        print()

        # Check before state
        print('BEFORE:')
        before = await conn.fetchrow('''
            SELECT datetime, indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 1
        ''', symbol)

        if before and before['indicators']:
            indicators = json.loads(before['indicators'])
            print(f'  RSI value: {indicators.get("daily_rsi_14", "NOT FOUND")}')
            print(f'  Avg gain state: {indicators.get("_daily_rsi_14_avg_gain", "NOT FOUND")}')
            print(f'  Avg loss state: {indicators.get("_daily_rsi_14_avg_loss", "NOT FOUND")}')
        print()

        # Run the cron function
        print('Running cron_calculate_rsi_for_symbol...')
        result = await conn.fetchrow('''
            SELECT * FROM cron_calculate_rsi_for_symbol($1, 'daily', 14)
        ''', symbol)

        print(f'Result:')
        print(f'  Status: {result["status"]}')
        print(f'  Updated rows: {result["updated_rows"]}')
        print(f'  RSI value: {result["rsi_value"]}')
        print(f'  Warning: {result["warning_message"]}')
        print(f'  Execution time: {result["execution_time_ms"]}ms')
        print()

        # Check after state
        print('AFTER:')
        after = await conn.fetchrow('''
            SELECT datetime, indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 1
        ''', symbol)

        if after and after['indicators']:
            indicators = json.loads(after['indicators'])
            print(f'  RSI value: {indicators.get("daily_rsi_14", "NOT FOUND")}')
            print(f'  Avg gain state: {indicators.get("_daily_rsi_14_avg_gain", "NOT FOUND")}')
            print(f'  Avg loss state: {indicators.get("_daily_rsi_14_avg_loss", "NOT FOUND")}')

            # Show all keys that start with underscore
            state_keys = [k for k in indicators.keys() if k.startswith('_')]
            if state_keys:
                print(f'  All state keys: {state_keys}')
            else:
                print('  No state keys found at all')
        print()

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_single_rsi())