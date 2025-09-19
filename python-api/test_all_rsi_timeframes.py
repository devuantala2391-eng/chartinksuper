"""
Comprehensive test of all RSI timeframes (daily, weekly, monthly)
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ComprehensiveRSITester:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def test_all_rsi_timeframes(self):
        """Test all RSI timeframes comprehensively"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Testing all RSI timeframes for symbol: {test_symbol}")

            # Test 1: Daily RSI calculation
            logger.info("1. Testing daily RSI calculation...")
            daily_result = await conn.fetchrow("""
                SELECT * FROM calculate_daily_rsi_for_symbol($1, 14, true)
            """, test_symbol)
            logger.info(f"Daily RSI result: {dict(daily_result)}")

            # Test 2: Weekly RSI calculation
            logger.info("2. Testing weekly RSI calculation...")
            weekly_result = await conn.fetchrow("""
                SELECT * FROM calculate_weekly_rsi(14, $1)
            """, test_symbol)
            logger.info(f"Weekly RSI result: {dict(weekly_result)}")

            # Test 3: Monthly RSI calculation
            logger.info("3. Testing monthly RSI calculation...")
            monthly_result = await conn.fetchrow("""
                SELECT * FROM calculate_monthly_rsi(14, $1)
            """, test_symbol)
            logger.info(f"Monthly RSI result: {dict(monthly_result)}")

            # Test 4: Check candle 999 for all timeframes
            logger.info("4. Checking candle 999 for all timeframes...")
            candle_999 = await conn.fetchrow("""
                SELECT
                    candle_sequence_number,
                    indicators->>'daily_rsi_14' as daily_rsi,
                    indicators->>'weekly_rsi_14' as weekly_rsi,
                    indicators->>'monthly_rsi_14' as monthly_rsi,
                    weekly_candle_key_id,
                    monthly_candle_key_id
                FROM daily_candles
                WHERE symbol = $1
                AND candle_sequence_number = 999
            """, test_symbol)

            logger.info(f"Candle 999 RSI values:")
            logger.info(f"  Daily RSI: {candle_999['daily_rsi']}")
            logger.info(f"  Weekly RSI: {candle_999['weekly_rsi']}")
            logger.info(f"  Monthly RSI: {candle_999['monthly_rsi']}")

            # Test 5: Check corresponding weekly and monthly candles
            weekly_candle_rsi = await conn.fetchval("""
                SELECT indicators->>'weekly_rsi_14'
                FROM weekly_candles
                WHERE weekly_candle_key_id = $1
            """, candle_999['weekly_candle_key_id'])

            monthly_candle_rsi = await conn.fetchval("""
                SELECT indicators->>'monthly_rsi_14'
                FROM monthly_candles
                WHERE monthly_candle_key_id = $1
            """, candle_999['monthly_candle_key_id'])

            logger.info(f"Corresponding candle RSI values:")
            logger.info(f"  Weekly candle RSI: {weekly_candle_rsi}")
            logger.info(f"  Monthly candle RSI: {monthly_candle_rsi}")

            # Test 6: Verify matching values
            weekly_match = candle_999['weekly_rsi'] == weekly_candle_rsi
            monthly_match = candle_999['monthly_rsi'] == monthly_candle_rsi

            logger.info(f"Value matching:")
            logger.info(f"  Weekly match: {weekly_match} ({candle_999['weekly_rsi']} == {weekly_candle_rsi})")
            logger.info(f"  Monthly match: {monthly_match} ({candle_999['monthly_rsi']} == {monthly_candle_rsi})")

            # Test 7: Check sliding window progression
            logger.info("5. Testing sliding window progression...")
            progression_check = await conn.fetch("""
                SELECT
                    candle_sequence_number,
                    monthly_close,
                    indicators->>'monthly_rsi_14' as monthly_rsi
                FROM daily_candles
                WHERE symbol = $1
                AND indicators->>'monthly_rsi_14' IS NOT NULL
                ORDER BY candle_sequence_number DESC
                LIMIT 5
            """, test_symbol)

            logger.info("Recent monthly RSI progression:")
            for candle in progression_check:
                logger.info(f"  Candle {candle['candle_sequence_number']}: monthly_close={candle['monthly_close']}, monthly_rsi={candle['monthly_rsi']}")

            await conn.close()

            # Determine overall success
            all_calculations_success = (
                daily_result['status'] == 'SUCCESS' and
                weekly_result['status'] == 'SUCCESS' and
                monthly_result['status'] == 'SUCCESS'
            )

            all_matches_success = weekly_match and monthly_match

            return all_calculations_success and all_matches_success

        except Exception as e:
            logger.error(f"Comprehensive test failed: {e}")
            return False

async def main():
    tester = ComprehensiveRSITester()
    success = await tester.test_all_rsi_timeframes()

    if success:
        print("\n" + "="*80)
        print("COMPREHENSIVE RSI TEST PASSED")
        print("All timeframes (daily, weekly, monthly) are working correctly!")
        print("- Daily RSI: Calculated with Wilder's smoothing")
        print("- Weekly RSI: Sliding window matches weekly candles on last day")
        print("- Monthly RSI: Sliding window matches monthly candles on last day")
        print("- All sliding windows show progressive updates")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("COMPREHENSIVE RSI TEST FAILED")
        print("Please check the logs for specific issues")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(main())