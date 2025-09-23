"""
Examine symbol 999 indicators for _0 suffix issue
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def examine_candle_999_indicators():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('=== EXAMINING SYMBOL 999 INDICATORS ===')
        print()

        # Get the latest few candles for symbol 999
        candles = await conn.fetch('''
            SELECT datetime, indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 5
        ''', '999')

        if not candles:
            print('No candles found for symbol 999')
            return

        print(f'Found {len(candles)} recent candles for symbol 999:')
        print()

        for i, candle in enumerate(candles):
            print(f'Candle {i+1}: {candle["datetime"]}')

            if candle['indicators']:
                indicators = json.loads(candle['indicators'])
                print(f'  Indicators ({len(indicators)} keys):')

                for key, value in indicators.items():
                    if key.startswith('_'):
                        print(f'    {key}: {value} <-- INTERNAL KEY')
                    else:
                        print(f'    {key}: {value}')

                        # Check for _0 suffix issue
                        if '_0' in key and not key.endswith('_0'):
                            print(f'      WARNING: Key contains _0 in middle: {key}')
                        elif key.endswith('_0'):
                            print(f'      ISSUE FOUND: Key ends with _0: {key}')
            else:
                print('  No indicators')
            print()

        # Check indicator_registry for comparison
        print('=== INDICATOR_REGISTRY CONFIGURATION ===')
        registry_indicators = await conn.fetch('SELECT * FROM indicator_registry')

        for ind in registry_indicators:
            config = json.loads(ind['config_data'])
            print(f'Registry: {config.get("name")} ({config.get("timeframe")}) params: {config.get("params")}')

        print()
        print('=== ANALYSIS ===')
        print('Looking for _0 suffix pattern in indicator keys...')

        # Analyze the pattern
        if candles and candles[0]['indicators']:
            latest_indicators = json.loads(candles[0]['indicators'])
            problematic_keys = []
            normal_keys = []

            for key in latest_indicators.keys():
                if key.endswith('_0') and not key.startswith('_'):
                    problematic_keys.append(key)
                elif not key.startswith('_'):
                    normal_keys.append(key)

            print(f'Normal indicator keys: {normal_keys}')
            print(f'Problematic keys with _0 suffix: {problematic_keys}')

            if problematic_keys:
                print()
                print('ISSUE IDENTIFIED: Keys ending with _0 suggest parameter formatting problem')
                print('This likely occurs in the cron indicator key generation logic')

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(examine_candle_999_indicators())