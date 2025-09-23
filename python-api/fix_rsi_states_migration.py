#!/usr/bin/env python3
"""
Migration script to fix RSI state issue:
1. Reload the fixed stored procedure
2. Populate RSI states for all symbols so cron can work incrementally
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_rsi_states():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('=== RSI STATE MIGRATION ===')
        print()

        # Step 1: Reload the fixed stored procedure
        print('1. Reloading fixed stored procedure...')
        with open('sql/stored_procedures/cron_calculate_rsi.sql', 'r') as f:
            procedure_sql = f.read()

        await conn.execute(procedure_sql)
        print('   [OK] Stored procedure updated successfully')
        print()

        # Step 2: Get all symbols that need RSI state population
        print('2. Finding symbols that need RSI state population...')
        symbols_query = '''
            SELECT DISTINCT symbol
            FROM daily_candles
            WHERE indicators ? 'daily_rsi_14'
            AND NOT indicators ? '_daily_rsi_14_avg_gain'
            ORDER BY symbol
        '''

        symbols = await conn.fetch(symbols_query)
        print(f'   Found {len(symbols)} symbols needing state population')
        print()

        if len(symbols) == 0:
            print('[OK] All symbols already have RSI states!')
            return

        # Step 3: Populate states for all symbols
        print('3. Populating RSI states (this will take a few minutes)...')
        success_count = 0
        error_count = 0

        for i, symbol_row in enumerate(symbols):
            symbol = symbol_row['symbol']

            try:
                # Use the fixed cron function to populate states
                result = await conn.fetchrow('''
                    SELECT * FROM cron_calculate_rsi_for_symbol($1, 'daily', 14)
                ''', symbol)

                if result['status'] in ['FALLBACK', 'SUCCESS']:
                    success_count += 1
                else:
                    error_count += 1
                    print(f'   ERROR {symbol}: {result.get("warning_message", "Unknown error")}')

                # Progress update every 500 symbols
                if (i + 1) % 500 == 0:
                    print(f'   Processed {i + 1}/{len(symbols)} symbols...')

            except Exception as e:
                error_count += 1
                print(f'   ERROR {symbol}: {e}')

        print()
        print('4. Verification...')

        # Step 4: Verify the fix
        verification = await conn.fetchrow('''
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                COUNT(DISTINCT CASE WHEN indicators ? '_daily_rsi_14_avg_gain' THEN symbol END) as symbols_with_state
            FROM daily_candles
            WHERE indicators ? 'daily_rsi_14'
        ''')

        total = verification['total_symbols']
        with_state = verification['symbols_with_state']

        print(f'   Total symbols with RSI: {total}')
        print(f'   Symbols with RSI state: {with_state}')
        print(f'   Successfully processed: {success_count}')
        print(f'   Errors: {error_count}')
        print()

        if with_state == total:
            print('[SUCCESS] All symbols now have RSI states!')
            print('[SUCCESS] Cron jobs will now use fast incremental calculations')
        else:
            missing = total - with_state
            print(f'[WARNING] {missing} symbols still missing RSI state')

        print()
        print('=== MIGRATION COMPLETE ===')

    except Exception as e:
        print(f'MIGRATION FAILED: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_rsi_states())