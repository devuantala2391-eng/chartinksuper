"""
Debug Monthly RSI Sliding Window Mismatch
Check why daily sliding window monthly RSI doesn't match monthly candle RSI on last day of month
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MonthlyRSIMismatchDebugger:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def debug_monthly_rsi_mismatch(self):
        """Debug the monthly RSI mismatch between daily sliding window and monthly candles"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Debugging monthly RSI mismatch for symbol: {test_symbol}")

            # Find a daily candle that's the last day of its month
            last_day_of_month = await conn.fetchrow("""
                SELECT
                    dc.candle_sequence_number,
                    dc.monthly_candle_key_id,
                    dc.monthly_open,
                    dc.monthly_high,
                    dc.monthly_low,
                    dc.monthly_close,
                    dc.indicators->>'monthly_rsi_14' as daily_monthly_rsi,
                    mc.month_sequence_number,
                    COUNT(*) OVER (PARTITION BY dc.monthly_candle_key_id) as total_days_in_month,
                    ROW_NUMBER() OVER (PARTITION BY dc.monthly_candle_key_id ORDER BY dc.candle_sequence_number DESC) as day_rank
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = $1
                AND dc.indicators->>'monthly_rsi_14' IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.candle_sequence_number DESC
                LIMIT 20
            """, test_symbol)

            if last_day_of_month and last_day_of_month['day_rank'] == 1:
                logger.info(f"Found last day of month: candle {last_day_of_month['candle_sequence_number']}")
                logger.info(f"Monthly OHLC: O={last_day_of_month['monthly_open']}, H={last_day_of_month['monthly_high']}, L={last_day_of_month['monthly_low']}, C={last_day_of_month['monthly_close']}")
                logger.info(f"Daily monthly_rsi: {last_day_of_month['daily_monthly_rsi']}")

                # Get the corresponding monthly candle
                monthly_candle = await conn.fetchrow("""
                    SELECT
                        monthly_candle_key_id,
                        month_sequence_number,
                        open as monthly_open,
                        high as monthly_high,
                        low as monthly_low,
                        close as monthly_close,
                        indicators->>'monthly_rsi_14' as monthly_rsi,
                        indicators->>'_monthly_rsi_14_avg_gain' as avg_gain,
                        indicators->>'_monthly_rsi_14_avg_loss' as avg_loss
                    FROM monthly_candles
                    WHERE monthly_candle_key_id = $1
                """, last_day_of_month['monthly_candle_key_id'])

                if monthly_candle:
                    logger.info(f"Monthly candle OHLC: O={monthly_candle['monthly_open']}, H={monthly_candle['monthly_high']}, L={monthly_candle['monthly_low']}, C={monthly_candle['monthly_close']}")
                    logger.info(f"Monthly candle monthly_rsi: {monthly_candle['monthly_rsi']}")
                    logger.info(f"Monthly RSI internal states: avg_gain={monthly_candle['avg_gain']}, avg_loss={monthly_candle['avg_loss']}")

                    # Check if OHLC values match
                    ohlc_match = (
                        last_day_of_month['monthly_open'] == monthly_candle['monthly_open'] and
                        last_day_of_month['monthly_high'] == monthly_candle['monthly_high'] and
                        last_day_of_month['monthly_low'] == monthly_candle['monthly_low'] and
                        last_day_of_month['monthly_close'] == monthly_candle['monthly_close']
                    )

                    logger.info(f"OHLC values match: {ohlc_match}")

                    if last_day_of_month['daily_monthly_rsi'] != monthly_candle['monthly_rsi']:
                        logger.error(f"MISMATCH FOUND! Daily={last_day_of_month['daily_monthly_rsi']} != Monthly={monthly_candle['monthly_rsi']}")

                        # Debug the calculation logic
                        logger.info("Debugging monthly calculation logic...")

                        # Get previous month's RSI state
                        prev_month = await conn.fetchrow("""
                            SELECT
                                close as prev_month_close,
                                indicators->>'_monthly_rsi_14_avg_gain' as prev_avg_gain,
                                indicators->>'_monthly_rsi_14_avg_loss' as prev_avg_loss
                            FROM monthly_candles
                            WHERE symbol = $1
                            AND month_sequence_number = $2 - 1
                        """, test_symbol, monthly_candle['month_sequence_number'])

                        if prev_month:
                            logger.info(f"Previous month: close={prev_month['prev_month_close']}, avg_gain={prev_month['prev_avg_gain']}, avg_loss={prev_month['prev_avg_loss']}")

                            # Calculate what the sliding window should produce
                            month_change = float(last_day_of_month['monthly_close']) - float(prev_month['prev_month_close'])
                            month_gain = max(month_change, 0)
                            month_loss = max(-month_change, 0)
                            alpha = 1.0 / 14

                            if prev_month['prev_avg_gain'] and prev_month['prev_avg_loss']:
                                prev_avg_gain = float(prev_month['prev_avg_gain'])
                                prev_avg_loss = float(prev_month['prev_avg_loss'])

                                current_avg_gain = prev_avg_gain + alpha * (month_gain - prev_avg_gain)
                                current_avg_loss = prev_avg_loss + alpha * (month_loss - prev_avg_loss)

                                if current_avg_loss == 0:
                                    calculated_rsi = 100
                                else:
                                    rs = current_avg_gain / current_avg_loss
                                    calculated_rsi = 100 - (100 / (1 + rs))

                                logger.info(f"Manual calculation:")
                                logger.info(f"  month_change={month_change}")
                                logger.info(f"  month_gain={month_gain}")
                                logger.info(f"  month_loss={month_loss}")
                                logger.info(f"  calculated_avg_gain={current_avg_gain}")
                                logger.info(f"  calculated_avg_loss={current_avg_loss}")
                                logger.info(f"  calculated_RSI={calculated_rsi}")
                                logger.info(f"  stored_avg_gain={monthly_candle['avg_gain']}")
                                logger.info(f"  stored_avg_loss={monthly_candle['avg_loss']}")

                                # Check what calculation method monthly candle used
                                stored_month_change = float(monthly_candle['monthly_close']) - float(prev_month['prev_month_close'])
                                logger.info(f"  monthly_candle_change={stored_month_change}")

                    else:
                        logger.info("VALUES MATCH CORRECTLY!")
            else:
                logger.warning("Could not find a last day of month candle to test")

            await conn.close()

        except Exception as e:
            logger.error(f"Debug failed: {e}")
            return False

async def main():
    debugger = MonthlyRSIMismatchDebugger()
    await debugger.debug_monthly_rsi_mismatch()

if __name__ == "__main__":
    asyncio.run(main())