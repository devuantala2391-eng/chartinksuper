"""
Check multiple monthly RSI values to find mismatches
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MultipleMonthlyRSIChecker:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def check_multiple_monthly_matches(self):
        """Check multiple monthly RSI values to find any mismatches"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Checking multiple monthly RSI matches for symbol: {test_symbol}")

            # Get all last days of months with their RSI values
            last_days_of_months = await conn.fetch("""
                WITH daily_with_rank AS (
                    SELECT
                        dc.candle_sequence_number,
                        dc.monthly_candle_key_id,
                        dc.monthly_close,
                        dc.indicators->>'monthly_rsi_14' as daily_monthly_rsi,
                        mc.month_sequence_number,
                        ROW_NUMBER() OVER (PARTITION BY dc.monthly_candle_key_id ORDER BY dc.candle_sequence_number DESC) as day_rank
                    FROM daily_candles dc
                    LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                    WHERE dc.symbol = $1
                    AND dc.indicators->>'monthly_rsi_14' IS NOT NULL
                    AND mc.month_sequence_number IS NOT NULL
                )
                SELECT
                    candle_sequence_number,
                    monthly_candle_key_id,
                    monthly_close,
                    daily_monthly_rsi,
                    month_sequence_number
                FROM daily_with_rank
                WHERE day_rank = 1
                ORDER BY month_sequence_number DESC
                LIMIT 10
            """, test_symbol)

            logger.info(f"Found {len(last_days_of_months)} last days of months to check")

            mismatches = []

            for daily_record in last_days_of_months:
                # Get corresponding monthly candle RSI
                monthly_candle = await conn.fetchrow("""
                    SELECT
                        close as monthly_close,
                        indicators->>'monthly_rsi_14' as monthly_rsi
                    FROM monthly_candles
                    WHERE monthly_candle_key_id = $1
                """, daily_record['monthly_candle_key_id'])

                daily_rsi = daily_record['daily_monthly_rsi']
                monthly_rsi = monthly_candle['monthly_rsi'] if monthly_candle else None

                logger.info(f"Month {daily_record['month_sequence_number']}, Candle {daily_record['candle_sequence_number']}: Daily={daily_rsi}, Monthly={monthly_rsi}")

                if daily_rsi != monthly_rsi:
                    mismatches.append({
                        'candle_sequence_number': daily_record['candle_sequence_number'],
                        'month_sequence_number': daily_record['month_sequence_number'],
                        'daily_rsi': daily_rsi,
                        'monthly_rsi': monthly_rsi,
                        'monthly_close': daily_record['monthly_close']
                    })

            if mismatches:
                logger.error(f"Found {len(mismatches)} mismatches:")
                for mismatch in mismatches:
                    logger.error(f"  Month {mismatch['month_sequence_number']}, Candle {mismatch['candle_sequence_number']}: {mismatch['daily_rsi']} != {mismatch['monthly_rsi']}")
            else:
                logger.info("All monthly RSI values match correctly!")

            # Also check some mid-month values to ensure sliding window is working
            logger.info("Checking mid-month sliding window behavior...")

            mid_month_sample = await conn.fetchrow("""
                SELECT
                    dc.candle_sequence_number,
                    dc.monthly_close,
                    dc.indicators->>'monthly_rsi_14' as daily_monthly_rsi,
                    mc.month_sequence_number,
                    mc.close as final_monthly_close,
                    mc.indicators->>'monthly_rsi_14' as final_monthly_rsi
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = $1
                AND dc.indicators->>'monthly_rsi_14' IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.candle_sequence_number DESC
                OFFSET 5
                LIMIT 1
            """, test_symbol)

            if mid_month_sample:
                logger.info(f"Mid-month sample - Candle {mid_month_sample['candle_sequence_number']}:")
                logger.info(f"  Current monthly_close: {mid_month_sample['monthly_close']}")
                logger.info(f"  Current sliding monthly_rsi: {mid_month_sample['daily_monthly_rsi']}")
                logger.info(f"  Final monthly_close: {mid_month_sample['final_monthly_close']}")
                logger.info(f"  Final monthly_rsi: {mid_month_sample['final_monthly_rsi']}")

                if mid_month_sample['monthly_close'] != mid_month_sample['final_monthly_close']:
                    logger.info("✓ Mid-month shows different monthly_close (sliding window working)")
                else:
                    logger.warning("Mid-month has same monthly_close as final (possible issue)")

            await conn.close()
            return len(mismatches) == 0

        except Exception as e:
            logger.error(f"Check failed: {e}")
            return False

async def main():
    checker = MultipleMonthlyRSIChecker()
    success = await checker.check_multiple_monthly_matches()

    if success:
        print("All monthly RSI values match correctly!")
    else:
        print("Found monthly RSI mismatches!")

if __name__ == "__main__":
    asyncio.run(main())