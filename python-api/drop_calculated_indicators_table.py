"""
Drop the calculated_indicators table from the database as part of consolidation
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def drop_calculated_indicators_table():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("Checking if calculated_indicators table exists...")

        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'calculated_indicators'
            )
        """)

        if table_exists:
            print("calculated_indicators table exists. Dropping it...")

            # Drop the table
            await conn.execute("DROP TABLE IF EXISTS calculated_indicators CASCADE")

            print("SUCCESS: calculated_indicators table has been dropped successfully!")
            print("System now uses indicator_registry as the single source of truth.")
        else:
            print("SUCCESS: calculated_indicators table does not exist (already removed).")

        # Verify indicator_registry exists
        registry_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'indicator_registry'
            )
        """)

        if registry_exists:
            # Count indicators in registry
            count = await conn.fetchval("SELECT COUNT(*) FROM indicator_registry")
            print(f"SUCCESS: indicator_registry table exists with {count} indicators.")
        else:
            print("WARNING: indicator_registry table does not exist!")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(drop_calculated_indicators_table())