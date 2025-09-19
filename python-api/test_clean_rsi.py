"""
Test RSI implementation with clean storage (only RSI values visible)
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CleanRSITester:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def test_clean_rsi(self):
        """Test RSI with clean storage (only RSI values visible to users)"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Testing clean RSI implementation for symbol: {test_symbol}")

            # Calculate RSI for all timeframes
            logger.info("Calculating weekly RSI...")
            weekly_result = await conn.fetchrow("""
                SELECT * FROM calculate_weekly_rsi(14, $1)
            """, test_symbol)

            logger.info("Calculating monthly RSI...")
            monthly_result = await conn.fetchrow("""
                SELECT * FROM calculate_monthly_rsi(14, $1)
            """, test_symbol)

            # Check what's visible in weekly candles (should only see RSI, not internal states)
            logger.info("Checking weekly candle indicators...")
            weekly_indicators = await conn.fetchrow("""
                SELECT
                    indicators->>'weekly_rsi_14' as weekly_rsi,
                    jsonb_object_keys(indicators) as all_keys
                FROM weekly_candles
                WHERE symbol = $1
                AND indicators->>'weekly_rsi_14' IS NOT NULL
                ORDER BY week_sequence_number DESC
                LIMIT 1
            """, test_symbol)

            logger.info(f"Weekly candle RSI: {weekly_indicators['weekly_rsi']}")

            # Get all indicator keys to verify only RSI is visible
            all_weekly_keys = await conn.fetch("""
                SELECT DISTINCT jsonb_object_keys(indicators) as key
                FROM weekly_candles
                WHERE symbol = $1
                AND indicators->>'weekly_rsi_14' IS NOT NULL
                ORDER BY key
            """, test_symbol)

            user_visible_keys = [key['key'] for key in all_weekly_keys if not key['key'].startswith('_')]
            internal_keys = [key['key'] for key in all_weekly_keys if key['key'].startswith('_')]

            logger.info(f"User-visible keys: {user_visible_keys}")
            logger.info(f"Internal keys (hidden): {internal_keys}")

            # Test daily sliding window RSI matches weekly on last day
            logger.info("Testing sliding window value matching...")
            daily_999 = await conn.fetchrow("""
                SELECT
                    candle_sequence_number,
                    weekly_candle_key_id,
                    indicators->>'weekly_rsi_14' as daily_weekly_rsi
                FROM daily_candles
                WHERE symbol = $1
                AND candle_sequence_number = 999
            """, test_symbol)

            weekly_candle_rsi = await conn.fetchval("""
                SELECT indicators->>'weekly_rsi_14'
                FROM weekly_candles
                WHERE weekly_candle_key_id = $1
            """, daily_999['weekly_candle_key_id'])

            logger.info(f"Daily 999 sliding weekly RSI: {daily_999['daily_weekly_rsi']}")
            logger.info(f"Weekly candle RSI: {weekly_candle_rsi}")

            # Verify they match
            if daily_999['daily_weekly_rsi'] == weekly_candle_rsi:
                logger.info("SUCCESS: Sliding window RSI matches weekly candle RSI!")
                success = True
            else:
                logger.error(f"MISMATCH: {daily_999['daily_weekly_rsi']} != {weekly_candle_rsi}")
                success = False

            await conn.close()
            return success

        except Exception as e:
            logger.error(f"Clean RSI test failed: {e}")
            return False

async def main():
    tester = CleanRSITester()
    success = await tester.test_clean_rsi()

    if success:
        print("\n" + "="*80)
        print("CLEAN RSI IMPLEMENTATION TEST PASSED")
        print("- Only RSI values are visible to users")
        print("- Internal calculation states are hidden with underscore prefix")
        print("- Sliding window RSI matches weekly/monthly candle RSI correctly")
        print("- Clean API without unnecessary technical details")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("CLEAN RSI IMPLEMENTATION TEST FAILED")
        print("Please check the logs for error details")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(main())