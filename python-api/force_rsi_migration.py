"""
Force RSI migration by dropping and recreating functions
"""
import asyncio
import asyncpg
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ForceRSIMigration:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def force_rsi_migration(self):
        """Force recreate RSI functions"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            logger.info("Dropping existing RSI functions...")

            # Drop RSI functions
            rsi_functions = [
                'calculate_daily_rsi_for_symbol',
                'calculate_weekly_rsi',
                'calculate_monthly_rsi',
                'update_daily_weekly_rsi',
                'update_daily_monthly_rsi'
            ]

            for func in rsi_functions:
                try:
                    await conn.execute(f"DROP FUNCTION IF EXISTS {func} CASCADE")
                    logger.info(f"Dropped {func}")
                except Exception as e:
                    logger.warning(f"Could not drop {func}: {e}")

            logger.info("Recreating RSI functions...")

            # Read and execute the updated RSI SQL
            sql_file_path = Path(__file__).parent / "sql" / "stored_procedures" / "calculate_rsi.sql"

            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            await conn.execute(sql_content)
            logger.info("RSI functions recreated successfully")

            await conn.close()
            return True

        except Exception as e:
            logger.error(f"Force migration failed: {e}")
            return False

async def main():
    migrator = ForceRSIMigration()
    success = await migrator.force_rsi_migration()

    if success:
        print("Force RSI migration completed successfully!")
    else:
        print("Force RSI migration failed!")

if __name__ == "__main__":
    asyncio.run(main())