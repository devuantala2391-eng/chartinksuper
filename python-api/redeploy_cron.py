"""
Redeploy the updated cron stored procedures to database
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

async def redeploy_cron_procedures():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print('Redeploying updated cron procedures...')

        # Read and execute the updated stored procedure
        sql_file = Path('sql/stored_procedures/cron_calculate_all_indicators.sql')
        if sql_file.exists():
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            await conn.execute(sql_content)
            print('SUCCESS: Successfully deployed updated cron procedures')
        else:
            print('ERROR: SQL file not found')

    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(redeploy_cron_procedures())