"""
Clean up old RSI gain/loss keys from weekly and monthly candles
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RSIKeyCleaner:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def clean_old_rsi_keys(self):
        """Remove old visible gain/loss keys, keep only RSI values and internal states"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            logger.info("Cleaning old RSI gain/loss keys from weekly candles...")

            # Clean weekly candles
            weekly_result = await conn.execute("""
                UPDATE weekly_candles
                SET indicators = indicators
                    - 'weekly_rsi_14_avg_gain'
                    - 'weekly_rsi_14_avg_loss'
                WHERE indicators ? 'weekly_rsi_14_avg_gain'
                   OR indicators ? 'weekly_rsi_14_avg_loss'
            """)

            logger.info(f"Cleaned weekly candles: {weekly_result}")

            # Clean monthly candles
            monthly_result = await conn.execute("""
                UPDATE monthly_candles
                SET indicators = indicators
                    - 'monthly_rsi_14_avg_gain'
                    - 'monthly_rsi_14_avg_loss'
                WHERE indicators ? 'monthly_rsi_14_avg_gain'
                   OR indicators ? 'monthly_rsi_14_avg_loss'
            """)

            logger.info(f"Cleaned monthly candles: {monthly_result}")

            # Verify cleanup
            remaining_weekly_keys = await conn.fetch("""
                SELECT DISTINCT jsonb_object_keys(indicators) as key
                FROM weekly_candles
                WHERE indicators->>'weekly_rsi_14' IS NOT NULL
                ORDER BY key
            """)

            remaining_monthly_keys = await conn.fetch("""
                SELECT DISTINCT jsonb_object_keys(indicators) as key
                FROM monthly_candles
                WHERE indicators->>'monthly_rsi_14' IS NOT NULL
                ORDER BY key
            """)

            logger.info(f"Remaining weekly keys: {[k['key'] for k in remaining_weekly_keys]}")
            logger.info(f"Remaining monthly keys: {[k['key'] for k in remaining_monthly_keys]}")

            await conn.close()
            return True

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return False

async def main():
    cleaner = RSIKeyCleaner()
    success = await cleaner.clean_old_rsi_keys()

    if success:
        print("Old RSI gain/loss keys cleaned successfully!")
    else:
        print("Cleanup failed!")

if __name__ == "__main__":
    asyncio.run(main())