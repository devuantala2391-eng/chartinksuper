#!/usr/bin/env python3
"""
Test if the stored procedure is properly loaded and debug what happens
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_stored_procedure():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        symbol = 'RELIANCE'
        print(f'=== TESTING STORED PROCEDURE FOR {symbol} ===')
        print()

        # First, reload the stored procedure to ensure it's updated
        print('1. Reloading stored procedure...')
        with open('sql/stored_procedures/cron_calculate_rsi.sql', 'r') as f:
            procedure_sql = f.read()

        await conn.execute(procedure_sql)
        print('   Stored procedure reloaded successfully')
        print()

        # Check the procedure exists
        exists = await conn.fetchval('''
            SELECT EXISTS(
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'public'
                AND p.proname = 'cron_calculate_rsi_for_symbol'
            )
        ''')
        print(f'2. Stored procedure exists: {exists}')
        print()

        # Run with verbose output
        print('3. Running stored procedure with NOTICE output...')

        # Enable NOTICE output
        await conn.execute("SET client_min_messages TO NOTICE")

        result = await conn.fetchrow('''
            SELECT * FROM cron_calculate_rsi_for_symbol($1, 'daily', 14)
        ''', symbol)

        print(f'   Status: {result["status"]}')
        print(f'   Updated rows: {result["updated_rows"]}')
        print(f'   Warning: {result["warning_message"]}')
        print()

        # Check the resulting indicators with all details
        indicators_row = await conn.fetchrow('''
            SELECT indicators
            FROM daily_candles
            WHERE symbol = $1
            ORDER BY datetime DESC
            LIMIT 1
        ''', symbol)

        if indicators_row and indicators_row['indicators']:
            indicators = json.loads(indicators_row['indicators'])
            print('4. All indicators in database:')
            for key, value in indicators.items():
                print(f'   {key}: {value}')
        print()

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_stored_procedure())