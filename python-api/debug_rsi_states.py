#!/usr/bin/env python3
"""
Debug script to check RSI states in the database
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check_rsi_states():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('=== CHECKING RSI STATES IN DATABASE ===')
        print()

        # Check a few symbols for their indicators
        test_symbols = ['JPPOWER', 'JSFB', 'RELIANCE']

        for symbol in test_symbols:
            print(f'Symbol: {symbol}')

            # Get latest candle indicators
            latest_candle = await conn.fetchrow('''
                SELECT datetime, indicators
                FROM daily_candles
                WHERE symbol = $1
                ORDER BY datetime DESC
                LIMIT 1
            ''', symbol)

            if latest_candle and latest_candle['indicators']:
                indicators = json.loads(latest_candle['indicators'])
                print(f'  Latest candle ({latest_candle["datetime"]}):')

                # Look for RSI and state keys
                rsi_keys = []
                state_keys = []

                for key, value in indicators.items():
                    if 'rsi' in key:
                        if key.startswith('_') and ('avg_gain' in key or 'avg_loss' in key):
                            state_keys.append(f"    {key}: {value}")
                        else:
                            rsi_keys.append(f"    {key}: {value}")

                if rsi_keys:
                    print('  RSI Values:')
                    for key in rsi_keys:
                        print(key)

                if state_keys:
                    print('  RSI State Keys:')
                    for key in state_keys:
                        print(key)
                else:
                    print('  [ERROR] NO RSI STATE KEYS FOUND!')

            else:
                print('  No indicators found')
            print()

        # Check how many symbols have RSI states
        result = await conn.fetchrow('''
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                COUNT(DISTINCT CASE WHEN indicators ? '_daily_rsi_14_avg_gain' THEN symbol END) as symbols_with_rsi_state
            FROM daily_candles
            WHERE indicators IS NOT NULL AND indicators != '{}'
        ''')

        print('=== SUMMARY ===')
        print(f'Total symbols with indicators: {result["total_symbols"]}')
        print(f'Symbols with RSI state: {result["symbols_with_rsi_state"]}')
        print(f'Missing RSI state: {result["total_symbols"] - result["symbols_with_rsi_state"]}')

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_rsi_states())