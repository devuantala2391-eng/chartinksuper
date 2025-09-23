"""
Test the fixed Bollinger Bands cron function
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_fixed_cron_bb():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('=== TESTING FIXED BOLLINGER BANDS CRON ===')
        print()

        # First clear the problematic _0 key from the database
        print('1. Cleaning up old indicator with _0 suffix...')
        await conn.execute('''
            UPDATE daily_candles
            SET indicators = indicators - $1
            WHERE symbol = $2
            AND indicators ? $1
        ''', 'daily_bb_20_2_0', '20MICRONS')
        print('   Removed daily_bb_20_2_0 key from 20MICRONS')
        print()

        # Run the cron function for Bollinger Bands
        print('2. Running fixed cron function...')
        results = await conn.fetch('''
            SELECT * FROM cron_calculate_all_indicators_for_symbol($1, 'daily')
        ''', '20MICRONS')

        print(f'   Cron returned {len(results)} results:')
        for result in results:
            print(f'     - {result["indicator_name"]}: {result["status"]} (updated {result["updated_rows"]} rows)')
        print()

        # Check the indicators now
        print('3. Checking updated indicators...')
        latest_candle = await conn.fetchrow('''
            SELECT datetime, indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 1
        ''', '20MICRONS')

        if latest_candle and latest_candle['indicators']:
            indicators = json.loads(latest_candle['indicators'])
            print(f'   Latest candle ({latest_candle["datetime"]}):')

            bb_keys = []
            for key, value in indicators.items():
                if 'bb' in key and not key.startswith('_'):
                    bb_keys.append(key)
                    print(f'     {key}: {value}')

            print()
            if len(bb_keys) == 1:
                print('SUCCESS: Only one Bollinger Bands key found (duplicate removed)')
                print(f'Correct key: {bb_keys[0]}')
            elif len(bb_keys) > 1:
                print('WARNING: Still multiple BB keys found')
                print(f'Keys: {bb_keys}')
            else:
                print('ERROR: No BB keys found')

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_fixed_cron_bb())