"""
Debug RSI Sliding Window Mismatch
Check why daily sliding window RSI doesn't match weekly candle RSI on last day of week
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RSIMismatchDebugger:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def debug_rsi_mismatch(self):
        """Debug the RSI mismatch between daily sliding window and weekly candles"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            # Get test symbol
            test_symbol = await conn.fetchval("SELECT symbol FROM daily_candles LIMIT 1")

            logger.info(f"Debugging RSI mismatch for symbol: {test_symbol}")

            # Check candle 999 specifically
            logger.info("Checking daily candle 999...")
            daily_999 = await conn.fetchrow("""
                SELECT
                    candle_sequence_number,
                    symbol,
                    weekly_candle_key_id,
                    weekly_open,
                    weekly_high,
                    weekly_low,
                    weekly_close,
                    indicators->>'weekly_rsi_14' as daily_weekly_rsi
                FROM daily_candles
                WHERE symbol = $1
                AND candle_sequence_number = 999
            """, test_symbol)

            if daily_999:
                logger.info(f"Daily 999: weekly_open={daily_999['weekly_open']}, weekly_close={daily_999['weekly_close']}, daily_weekly_rsi={daily_999['daily_weekly_rsi']}")
                weekly_candle_key = daily_999['weekly_candle_key_id']

                # Get the corresponding weekly candle
                weekly_candle = await conn.fetchrow("""
                    SELECT
                        weekly_candle_key_id,
                        week_sequence_number,
                        open as weekly_open,
                        high as weekly_high,
                        low as weekly_low,
                        close as weekly_close,
                        indicators->>'weekly_rsi_14' as weekly_rsi,
                        indicators->>'weekly_rsi_14_avg_gain' as avg_gain,
                        indicators->>'weekly_rsi_14_avg_loss' as avg_loss
                    FROM weekly_candles
                    WHERE weekly_candle_key_id = $1
                """, weekly_candle_key)

                if weekly_candle:
                    logger.info(f"Weekly candle: open={weekly_candle['weekly_open']}, close={weekly_candle['weekly_close']}, weekly_rsi={weekly_candle['weekly_rsi']}")
                    logger.info(f"Weekly RSI states: avg_gain={weekly_candle['avg_gain']}, avg_loss={weekly_candle['avg_loss']}")

                    # Check if this is the last day of the week
                    last_day_check = await conn.fetchrow("""
                        SELECT
                            COUNT(*) as total_days_in_week,
                            MAX(candle_sequence_number) as last_day_seq
                        FROM daily_candles
                        WHERE weekly_candle_key_id = $1
                    """, weekly_candle_key)

                    logger.info(f"Week info: total_days={last_day_check['total_days_in_week']}, last_day_seq={last_day_check['last_day_seq']}")

                    if daily_999['candle_sequence_number'] == last_day_check['last_day_seq']:
                        logger.info("✓ Candle 999 IS the last day of its week")
                        logger.info(f"Expected match: Daily weekly_rsi={daily_999['daily_weekly_rsi']} should equal Weekly RSI={weekly_candle['weekly_rsi']}")

                        if daily_999['daily_weekly_rsi'] != weekly_candle['weekly_rsi']:
                            logger.error(f"❌ MISMATCH FOUND! Daily={daily_999['daily_weekly_rsi']} != Weekly={weekly_candle['weekly_rsi']}")

                            # Check the calculation logic
                            logger.info("Debugging calculation logic...")

                            # Get previous week's RSI state
                            prev_week = await conn.fetchrow("""
                                SELECT
                                    indicators->>'weekly_rsi_14_avg_gain' as prev_avg_gain,
                                    indicators->>'weekly_rsi_14_avg_loss' as prev_avg_loss
                                FROM weekly_candles
                                WHERE symbol = $1
                                AND week_sequence_number = $2 - 1
                            """, test_symbol, weekly_candle['week_sequence_number'])

                            if prev_week:
                                logger.info(f"Previous week RSI states: avg_gain={prev_week['prev_avg_gain']}, avg_loss={prev_week['prev_avg_loss']}")

                                # Calculate what the sliding window should produce
                                week_change = float(daily_999['weekly_close']) - float(daily_999['weekly_open'])
                                week_gain = max(week_change, 0)
                                week_loss = max(-week_change, 0)
                                alpha = 1.0 / 14

                                if prev_week['prev_avg_gain'] and prev_week['prev_avg_loss']:
                                    prev_avg_gain = float(prev_week['prev_avg_gain'])
                                    prev_avg_loss = float(prev_week['prev_avg_loss'])

                                    current_avg_gain = prev_avg_gain + alpha * (week_gain - prev_avg_gain)
                                    current_avg_loss = prev_avg_loss + alpha * (week_loss - prev_avg_loss)

                                    if current_avg_loss == 0:
                                        calculated_rsi = 100
                                    else:
                                        rs = current_avg_gain / current_avg_loss
                                        calculated_rsi = 100 - (100 / (1 + rs))

                                    logger.info(f"Manual calculation: week_change={week_change}, week_gain={week_gain}, week_loss={week_loss}")
                                    logger.info(f"Sliding window result: avg_gain={current_avg_gain}, avg_loss={current_avg_loss}, RSI={calculated_rsi}")
                        else:
                            logger.info("✓ Values match correctly!")
                    else:
                        logger.info("Candle 999 is not the last day of its week")

            await conn.close()

        except Exception as e:
            logger.error(f"Debug failed: {e}")
            return False

async def main():
    debugger = RSIMismatchDebugger()
    await debugger.debug_rsi_mismatch()

if __name__ == "__main__":
    asyncio.run(main())