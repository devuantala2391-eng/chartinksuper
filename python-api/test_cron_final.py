"""
Final test of the cron indicator system
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_individual_functions():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    symbol = '20MICRONS'
    timeframe = 'daily'
    period = 14

    print('Testing individual cron functions...')

    # Test each cron function individually
    functions_to_test = [
        ('RSI', 'cron_calculate_rsi_for_symbol', [symbol, timeframe, period]),
        ('ATR', 'cron_calculate_atr_for_symbol', [symbol, timeframe, period]),
        ('EMA', 'cron_calculate_ema_for_symbol', [symbol, timeframe, 20]),
        ('SMA', 'cron_calculate_sma_for_symbol', [symbol, timeframe, 20]),
        ('Percentage Change', 'cron_calculate_percentage_change_for_symbol', [symbol, timeframe])
    ]

    for name, func_name, params in functions_to_test:
        try:
            query = f"SELECT * FROM {func_name}(" + ', '.join(['$' + str(i+1) for i in range(len(params))]) + ")"
            results = await conn.fetch(query, *params)

            print(f"SUCCESS: {name} - {len(results)} results")
            if results:
                result = results[0]
                print(f"   Status: {result.get('status', 'N/A')}")
                print(f"   Warning: {result.get('warning_message', 'None')}")

        except Exception as e:
            print(f"ERROR: {name} - {e}")

    print('\nTesting master function...')
    try:
        results = await conn.fetch(
            "SELECT * FROM cron_calculate_all_indicators_for_symbol($1, $2)",
            symbol, timeframe
        )
        print(f"SUCCESS: Master function - {len(results)} results")

    except Exception as e:
        print(f"ERROR: Master function - {e}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(test_individual_functions())