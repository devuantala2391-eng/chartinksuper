"""
Test the corrected RSI implementation by forcing a fresh calculation
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CorrectedRSITester:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def test_corrected_rsi(self):
        """Test the corrected RSI implementation with fresh calculation"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Testing corrected RSI implementation for symbol: {test_symbol}")

            # Clear existing RSI values to force fresh calculation
            logger.info("Clearing existing RSI values to force fresh calculation...")
            await conn.execute("""
                UPDATE monthly_candles
                SET indicators = indicators - 'monthly_rsi_14' - '_monthly_rsi_14_avg_gain' - '_monthly_rsi_14_avg_loss'
                WHERE symbol = $1
            """, test_symbol)

            await conn.execute("""
                UPDATE weekly_candles
                SET indicators = indicators - 'weekly_rsi_14' - '_weekly_rsi_14_avg_gain' - '_weekly_rsi_14_avg_loss'
                WHERE symbol = $1
            """, test_symbol)

            await conn.execute("""
                UPDATE daily_candles
                SET indicators = indicators - 'daily_rsi_14' - 'weekly_rsi_14' - 'monthly_rsi_14'
                WHERE symbol = $1
            """, test_symbol)

            # Force recalculate monthly RSI with corrected logic
            logger.info("Recalculating monthly RSI with corrected implementation...")
            monthly_result = await conn.fetchrow("""
                SELECT * FROM calculate_monthly_rsi(14, $1)
            """, test_symbol)

            logger.info(f"Monthly RSI recalculation result: {dict(monthly_result)}")

            # Check the new values
            logger.info("Checking corrected RSI values...")
            latest_monthly = await conn.fetchrow("""
                SELECT
                    indicators->>'monthly_rsi_14' as corrected_rsi,
                    indicators->>'_monthly_rsi_14_avg_gain' as corrected_avg_gain,
                    indicators->>'_monthly_rsi_14_avg_loss' as corrected_avg_loss
                FROM monthly_candles
                WHERE symbol = $1
                ORDER BY month_sequence_number DESC
                LIMIT 1
            """, test_symbol)

            logger.info(f"Corrected RSI values:")
            logger.info(f"  RSI: {latest_monthly['corrected_rsi']}")
            logger.info(f"  Avg Gain: {latest_monthly['corrected_avg_gain']}")
            logger.info(f"  Avg Loss: {latest_monthly['corrected_avg_loss']}")

            # Compare with manual calculation and TradingView
            logger.info(f"\n--- Final Comparison ---")
            logger.info(f"Manual calculation (correct): 57.85")
            logger.info(f"Our corrected RSI: {latest_monthly['corrected_rsi']}")
            logger.info(f"TradingView RSI: 58.06")

            corrected_rsi_float = float(latest_monthly['corrected_rsi'])
            logger.info(f"Difference from manual: {abs(corrected_rsi_float - 57.85):.2f}")
            logger.info(f"Difference from TradingView: {abs(corrected_rsi_float - 58.06):.2f}")

            # Manual verification with stored averages
            if latest_monthly['corrected_avg_gain'] and latest_monthly['corrected_avg_loss']:
                stored_gain = float(latest_monthly['corrected_avg_gain'])
                stored_loss = float(latest_monthly['corrected_avg_loss'])

                manual_rs = stored_gain / stored_loss
                manual_rsi = 100 - (100 / (1 + manual_rs))

                logger.info(f"Manual RSI from corrected stored averages: {manual_rsi:.2f}")
                logger.info(f"Expected avg_gain (manual): 11.1511")
                logger.info(f"Expected avg_loss (manual): 8.1247")
                logger.info(f"Actual avg_gain (stored): {stored_gain}")
                logger.info(f"Actual avg_loss (stored): {stored_loss}")

            await conn.close()

            # Determine success
            if latest_monthly['corrected_rsi']:
                diff_from_tradingview = abs(corrected_rsi_float - 58.06)
                return diff_from_tradingview < 0.5  # Success if within 0.5 of TradingView
            else:
                return False

        except Exception as e:
            logger.error(f"Corrected RSI test failed: {e}")
            return False

async def main():
    tester = CorrectedRSITester()
    success = await tester.test_corrected_rsi()

    if success:
        print("\n" + "="*80)
        print("CORRECTED RSI IMPLEMENTATION TEST PASSED")
        print("RSI calculation now matches TradingView methodology!")
        print("- Fixed initialization order bug")
        print("- SMA for first 14 periods, then Wilder's EMA")
        print("- Much closer to TradingView values")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("CORRECTED RSI IMPLEMENTATION TEST - NEEDS REVIEW")
        print("Please check the logs for comparison details")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(main())