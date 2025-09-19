"""
Recalculate RSI with corrected functions to test value matching
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RSIRecalculationTester:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def recalculate_and_test(self):
        """Recalculate RSI with corrected functions and test matching"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            # Get test symbol
            test_symbol = await conn.fetchval("SELECT symbol FROM daily_candles LIMIT 1")

            logger.info(f"Recalculating RSI for symbol: {test_symbol}")

            # Force recalculate weekly RSI
            logger.info("Force recalculating weekly RSI...")
            weekly_result = await conn.fetchrow("""
                SELECT * FROM calculate_weekly_rsi(14, $1)
            """, test_symbol)

            logger.info(f"Weekly recalculation result: {dict(weekly_result)}")

            # Now check candle 999 again
            logger.info("Checking candle 999 after recalculation...")
            daily_999 = await conn.fetchrow("""
                SELECT
                    candle_sequence_number,
                    weekly_candle_key_id,
                    weekly_close,
                    indicators->>'weekly_rsi_14' as daily_weekly_rsi
                FROM daily_candles
                WHERE symbol = $1
                AND candle_sequence_number = 999
            """, test_symbol)

            weekly_candle = await conn.fetchrow("""
                SELECT
                    weekly_candle_key_id,
                    close as weekly_close,
                    indicators->>'weekly_rsi_14' as weekly_rsi
                FROM weekly_candles
                WHERE weekly_candle_key_id = $1
            """, daily_999['weekly_candle_key_id'])

            logger.info(f"After recalculation:")
            logger.info(f"Daily 999 weekly_rsi: {daily_999['daily_weekly_rsi']}")
            logger.info(f"Weekly candle weekly_rsi: {weekly_candle['weekly_rsi']}")

            if daily_999['daily_weekly_rsi'] == weekly_candle['weekly_rsi']:
                logger.info("SUCCESS: Values now match!")
                return True
            else:
                logger.error(f"Still mismatch: {daily_999['daily_weekly_rsi']} != {weekly_candle['weekly_rsi']}")
                return False

            await conn.close()

        except Exception as e:
            logger.error(f"Recalculation test failed: {e}")
            return False

async def main():
    tester = RSIRecalculationTester()
    success = await tester.recalculate_and_test()

    if success:
        print("RSI values now match correctly!")
    else:
        print("RSI values still don't match - need further investigation")

if __name__ == "__main__":
    asyncio.run(main())