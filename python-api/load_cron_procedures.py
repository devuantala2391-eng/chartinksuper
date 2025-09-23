"""
Load all cron stored procedures into the database
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def load_procedures():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("Loading cron stored procedures...")

        # List of procedure files to load
        procedure_files = [
            'cron_calculate_rsi.sql',
            'cron_calculate_atr.sql',
            'cron_calculate_ema.sql',
            'cron_calculate_remaining_indicators.sql',
            'cron_calculate_all_indicators.sql'
        ]

        base_path = "D:/chartinksuper/python-api/sql/stored_procedures"

        for file_name in procedure_files:
            file_path = f"{base_path}/{file_name}"

            if os.path.exists(file_path):
                print(f"Loading {file_name}...")

                with open(file_path, 'r', encoding='utf-8') as f:
                    sql_content = f.read()

                try:
                    await conn.execute(sql_content)
                    print(f"   SUCCESS: Successfully loaded {file_name}")
                except Exception as e:
                    print(f"   ERROR: Failed to load {file_name}: {e}")
            else:
                print(f"   ERROR: File not found: {file_path}")

        print("\nTesting function exists...")
        try:
            # Test if the main function exists
            result = await conn.fetchrow("""
                SELECT proname
                FROM pg_proc
                WHERE proname = 'cron_calculate_all_indicators_for_symbol'
            """)

            if result:
                print("SUCCESS: cron_calculate_all_indicators_for_symbol function exists")
            else:
                print("ERROR: cron_calculate_all_indicators_for_symbol function not found")

        except Exception as e:
            print(f"Error checking function: {e}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(load_procedures())