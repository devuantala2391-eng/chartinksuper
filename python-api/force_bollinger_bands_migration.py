"""
Force Bollinger Bands migration by applying only the Bollinger Bands SQL
"""
import asyncio
import asyncpg
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ForceBollingerBandsMigration:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def force_bollinger_bands_migration(self):
        """Force apply Bollinger Bands functions"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            logger.info("Applying Bollinger Bands migration...")

            # Read and execute the Bollinger Bands SQL
            sql_file_path = Path(__file__).parent / "sql" / "stored_procedures" / "calculate_bollinger_bands.sql"

            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            await conn.execute(sql_content)
            logger.info("Bollinger Bands functions created successfully")

            # Verify functions were created
            bb_functions = [
                'calculate_daily_bollinger_bands_for_symbol',
                'calculate_weekly_bollinger_bands',
                'calculate_monthly_bollinger_bands',
                'update_daily_weekly_bollinger_bands',
                'update_daily_monthly_bollinger_bands',
                'format_multiplier_param'
            ]

            existing_functions = await conn.fetch("""
                SELECT routine_name FROM information_schema.routines
                WHERE routine_schema = 'public'
                AND routine_type = 'FUNCTION'
                AND routine_name = ANY($1)
            """, bb_functions)

            created_functions = [func['routine_name'] for func in existing_functions]
            logger.info(f"Created Bollinger Bands functions: {created_functions}")

            missing_functions = set(bb_functions) - set(created_functions)
            if missing_functions:
                logger.warning(f"Missing functions: {missing_functions}")
            else:
                logger.info("✅ All Bollinger Bands functions created successfully")

            await conn.close()
            return len(missing_functions) == 0

        except Exception as e:
            logger.error(f"Force migration failed: {e}")
            return False

async def main():
    migrator = ForceBollingerBandsMigration()
    success = await migrator.force_bollinger_bands_migration()

    if success:
        print("Force Bollinger Bands migration completed successfully!")
    else:
        print("Force Bollinger Bands migration failed!")

if __name__ == "__main__":
    asyncio.run(main())