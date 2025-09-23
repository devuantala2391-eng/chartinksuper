"""
Check the calculated_indicators table to understand the current state
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check_table():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        # Check table structure
        print("Checking calculated_indicators table structure...")
        structure = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'calculated_indicators'
            ORDER BY ordinal_position
        """)

        for col in structure:
            print(f"   {col['column_name']}: {col['data_type']}")

        # Check total count
        total_count = await conn.fetchrow("SELECT COUNT(*) as count FROM calculated_indicators")
        print(f"\nTotal indicators in table: {total_count['count']}")

        if total_count['count'] > 0:
            # Check by status
            status_counts = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM calculated_indicators
                GROUP BY status
            """)

            print("\nIndicators by status:")
            for status in status_counts:
                print(f"   {status['status']}: {status['count']}")

            # Show sample data
            print("\nSample indicators:")
            samples = await conn.fetch("""
                SELECT indicator_name, timeframe, parameters, status, indicator_key
                FROM calculated_indicators
                LIMIT 10
            """)

            for sample in samples:
                params = json.loads(sample['parameters']) if sample['parameters'] else {}
                print(f"   {sample['indicator_name']} ({sample['timeframe']}): {params} -> {sample['status']}")

        else:
            print("Table is empty - no indicators have been registered yet")

        # Check if there are any indicators in the daily_candles table
        print("\nChecking for existing indicator data in daily_candles...")
        sample_candle = await conn.fetchrow("""
            SELECT indicators
            FROM daily_candles
            WHERE indicators IS NOT NULL
            AND jsonb_typeof(indicators) = 'object'
            LIMIT 1
        """)

        if sample_candle:
            indicators = json.loads(sample_candle['indicators'])
            print(f"Found indicator data in daily_candles. Sample keys: {list(indicators.keys())[:10]}")
        else:
            print("No indicator data found in daily_candles")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_table())