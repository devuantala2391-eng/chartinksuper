"""
Debug the function call to see exactly what's happening
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_function():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("Testing simple query first...")

        # Test basic query
        result = await conn.fetchrow("""
            SELECT indicator_name, timeframe, parameters
            FROM calculated_indicators
            WHERE status = 'active'
            AND timeframe = 'daily'
            LIMIT 1
        """)

        if result:
            print(f"Sample indicator: {result['indicator_name']} ({result['timeframe']})")

            # Test function call
            print("Testing function call...")
            symbol = '20MICRONS'
            timeframe = 'daily'

            try:
                results = await conn.fetch(
                    "SELECT * FROM cron_calculate_all_indicators_for_symbol($1, $2)",
                    symbol, timeframe
                )
                print(f"Function returned {len(results)} results")
                for result in results[:3]:  # Show first 3 results
                    print(f"   {result}")

            except Exception as e:
                print(f"Function call error: {e}")

                # Let's check what functions exist
                functions = await conn.fetch("""
                    SELECT proname, pronargs
                    FROM pg_proc
                    WHERE proname LIKE 'cron_calculate%'
                """)

                print("\nAvailable cron functions:")
                for func in functions:
                    print(f"   {func['proname']} ({func['pronargs']} args)")

        else:
            print("No indicators found")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_function())