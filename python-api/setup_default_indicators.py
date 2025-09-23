"""
Setup default indicators in the indicator_registry table
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def setup_default_indicators():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("Setting up default indicators...")

        # Define common indicators that should be calculated
        default_indicators = [
            # RSI indicators
            {'name': 'rsi', 'timeframe': 'daily', 'parameters': {'period': 14}},
            {'name': 'rsi', 'timeframe': 'weekly', 'parameters': {'period': 14}},
            {'name': 'rsi', 'timeframe': 'monthly', 'parameters': {'period': 14}},

            # EMA indicators
            {'name': 'ema', 'timeframe': 'daily', 'parameters': {'period': 20}},
            {'name': 'ema', 'timeframe': 'weekly', 'parameters': {'period': 20}},
            {'name': 'ema', 'timeframe': 'monthly', 'parameters': {'period': 20}},

            # SMA indicators
            {'name': 'sma', 'timeframe': 'daily', 'parameters': {'period': 20}},
            {'name': 'sma', 'timeframe': 'weekly', 'parameters': {'period': 20}},
            {'name': 'sma', 'timeframe': 'monthly', 'parameters': {'period': 20}},

            # ATR indicators
            {'name': 'atr', 'timeframe': 'daily', 'parameters': {'period': 14}},
            {'name': 'atr', 'timeframe': 'weekly', 'parameters': {'period': 14}},
            {'name': 'atr', 'timeframe': 'monthly', 'parameters': {'period': 14}},

            # Bollinger Bands
            {'name': 'bollinger_bands', 'timeframe': 'daily', 'parameters': {'period': 20, 'multiplier': 2.0}},
            {'name': 'bollinger_bands', 'timeframe': 'weekly', 'parameters': {'period': 20, 'multiplier': 2.0}},
            {'name': 'bollinger_bands', 'timeframe': 'monthly', 'parameters': {'period': 20, 'multiplier': 2.0}},

            # SuperTrend
            {'name': 'supertrend', 'timeframe': 'daily', 'parameters': {'period': 10, 'multiplier': 2.0}},
            {'name': 'supertrend', 'timeframe': 'weekly', 'parameters': {'period': 10, 'multiplier': 2.0}},
            {'name': 'supertrend', 'timeframe': 'monthly', 'parameters': {'period': 10, 'multiplier': 2.0}},

            # Percentage Change
            {'name': 'percentage_change', 'timeframe': 'daily', 'parameters': {}},
            {'name': 'percentage_change', 'timeframe': 'weekly', 'parameters': {}},
            {'name': 'percentage_change', 'timeframe': 'monthly', 'parameters': {}},
        ]

        registered_count = 0

        for indicator in default_indicators:
            # Create config_data for indicator_registry
            config_data = {
                'name': indicator['name'],
                'timeframe': indicator['timeframe'],
                'params': indicator['parameters']
            }

            # Check if already exists in indicator_registry
            existing = await conn.fetchrow(
                "SELECT id FROM indicator_registry WHERE config_data = $1",
                json.dumps(config_data)
            )

            if not existing:
                # Insert new indicator into indicator_registry
                await conn.execute("""
                    INSERT INTO indicator_registry (
                        config_data, created_at, updated_at
                    ) VALUES ($1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                json.dumps(config_data)
                )

                print(f"   Registered: {indicator['name']} ({indicator['timeframe']}) with params {indicator['parameters']}")
                registered_count += 1
            else:
                print(f"   Already exists: {indicator['name']} ({indicator['timeframe']}) with params {indicator['parameters']}")

        print(f"\nRegistered {registered_count} new indicators")

        # Show final summary
        final_count = await conn.fetchrow("SELECT COUNT(*) as count FROM indicator_registry")
        print(f"Total indicators in registry: {final_count['count']}")

        # Show all registered indicators grouped by timeframe
        indicators_by_timeframe = await conn.fetch("""
            SELECT config_data
            FROM indicator_registry
            ORDER BY config_data->>'timeframe', config_data->>'name'
        """)

        timeframe_groups = {}
        for ind in indicators_by_timeframe:
            config = json.loads(ind['config_data'])
            timeframe = config.get('timeframe', 'daily')
            name = config.get('name', 'unknown')
            params = config.get('params', {})

            if timeframe not in timeframe_groups:
                timeframe_groups[timeframe] = []
            timeframe_groups[timeframe].append(f"{name}: {params}")

        for timeframe, indicators in timeframe_groups.items():
            print(f"\n{timeframe.upper()} indicators:")
            for indicator in indicators:
                print(f"   {indicator}")

    finally:
        await conn.close()

# Note: No longer using indicator keys - using JSON config directly in indicator_registry

if __name__ == "__main__":
    asyncio.run(setup_default_indicators())