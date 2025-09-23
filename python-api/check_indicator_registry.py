"""
Check the indicator_registry table
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def check_registry():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        # Check if indicator_registry table exists
        table_exists = await conn.fetchrow("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'indicator_registry'
            )
        """)

        if table_exists['exists']:
            print("indicator_registry table exists")

            # Check content
            total_count = await conn.fetchrow("SELECT COUNT(*) as count FROM indicator_registry")
            print(f"Total entries: {total_count['count']}")

            if total_count['count'] > 0:
                # Show all entries
                entries = await conn.fetch("SELECT * FROM indicator_registry")
                for entry in entries:
                    params = json.loads(entry['parameters']) if entry['parameters'] else {}
                    timeframes = json.loads(entry['timeframes']) if entry['timeframes'] else []
                    print(f"   {entry['name']}: {params}, timeframes: {timeframes}, enabled: {entry['enabled']}")

        else:
            print("indicator_registry table does not exist")

        # Also check what tables do exist
        print("\nAll tables in database:")
        all_tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        for table in all_tables:
            print(f"   {table['table_name']}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_registry())