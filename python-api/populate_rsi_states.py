#!/usr/bin/env python3
"""
Populate missing RSI states after hard-refresh
This will calculate and save the RSI state keys (_avg_gain, _avg_loss)
so that cron can work incrementally instead of falling back to full history
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def populate_rsi_states():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('=== POPULATING RSI STATES FOR ALL SYMBOLS ===')
        print()

        # Get all symbols that have RSI but no state keys
        symbols_query = '''
            SELECT DISTINCT symbol
            FROM daily_candles
            WHERE indicators ? 'daily_rsi_14'
            AND NOT indicators ? '_daily_rsi_14_avg_gain'
            ORDER BY symbol
        '''

        symbols = await conn.fetch(symbols_query)
        print(f'Found {len(symbols)} symbols needing RSI state population')
        print()

        success_count = 0
        for i, symbol_row in enumerate(symbols):
            symbol = symbol_row['symbol']

            try:
                # Use the fallback calculation from cron to populate states
                # This will calculate full RSI and save the state keys
                result = await conn.fetchrow('''
                    SELECT * FROM cron_calculate_rsi_for_symbol($1, 'daily', 14)
                ''', symbol)

                if result['status'] == 'FALLBACK':
                    success_count += 1
                    if (i + 1) % 100 == 0 or i == 0:
                        print(f'Processed {i + 1}/{len(symbols)}: {symbol} - State populated')
                elif result['status'] == 'SUCCESS':
                    success_count += 1
                    if (i + 1) % 100 == 0 or i == 0:
                        print(f'Processed {i + 1}/{len(symbols)}: {symbol} - Already had state')
                else:
                    print(f'FAILED {symbol}: {result.get("warning_message", "Unknown error")}')

            except Exception as e:
                print(f'ERROR processing {symbol}: {e}')

        print()
        print('=== VERIFICATION ===')

        # Check how many symbols now have RSI states
        result = await conn.fetchrow('''
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                COUNT(DISTINCT CASE WHEN indicators ? '_daily_rsi_14_avg_gain' THEN symbol END) as symbols_with_rsi_state
            FROM daily_candles
            WHERE indicators ? 'daily_rsi_14'
        ''')

        print(f'Symbols with RSI values: {result["total_symbols"]}')
        print(f'Symbols with RSI state: {result["symbols_with_rsi_state"]}')
        print(f'Successfully populated: {success_count}')

        if result["symbols_with_rsi_state"] == result["total_symbols"]:
            print('SUCCESS: All symbols now have RSI states!')
        else:
            print(f'Still missing state for {result["total_symbols"] - result["symbols_with_rsi_state"]} symbols')

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(populate_rsi_states())