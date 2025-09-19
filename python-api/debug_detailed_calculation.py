"""
Debug detailed RSI calculation to understand the mismatch
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DetailedRSIDebugger:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def debug_detailed_calculation(self):
        """Debug the detailed RSI calculation step by step"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            # Get the weekly candle for candle 999
            weekly_info = await conn.fetchrow("""
                SELECT
                    dc.weekly_candle_key_id,
                    wc.week_sequence_number,
                    wc.close as current_week_close,
                    wc.indicators->>'weekly_rsi_14_avg_gain' as current_avg_gain,
                    wc.indicators->>'weekly_rsi_14_avg_loss' as current_avg_loss
                FROM daily_candles dc
                JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = $1 AND dc.candle_sequence_number = 999
            """, test_symbol)

            logger.info(f"Current week (999): close={weekly_info['current_week_close']}, avg_gain={weekly_info['current_avg_gain']}, avg_loss={weekly_info['current_avg_loss']}")

            # Get the previous week's data
            prev_week_info = await conn.fetchrow("""
                SELECT
                    close as prev_week_close,
                    indicators->>'weekly_rsi_14_avg_gain' as prev_avg_gain,
                    indicators->>'weekly_rsi_14_avg_loss' as prev_avg_loss
                FROM weekly_candles
                WHERE symbol = $1
                AND week_sequence_number = $2 - 1
            """, test_symbol, weekly_info['week_sequence_number'])

            logger.info(f"Previous week: close={prev_week_info['prev_week_close']}, avg_gain={prev_week_info['prev_avg_gain']}, avg_loss={prev_week_info['prev_avg_loss']}")

            # Calculate what weekly RSI should be
            if prev_week_info['prev_week_close']:
                week_change = float(weekly_info['current_week_close']) - float(prev_week_info['prev_week_close'])
                week_gain = max(week_change, 0)
                week_loss = max(-week_change, 0)
                alpha = 1.0 / 14

                # Manual calculation using Wilder's smoothing
                if prev_week_info['prev_avg_gain'] and prev_week_info['prev_avg_loss']:
                    calculated_avg_gain = float(prev_week_info['prev_avg_gain']) + alpha * (week_gain - float(prev_week_info['prev_avg_gain']))
                    calculated_avg_loss = float(prev_week_info['prev_avg_loss']) + alpha * (week_loss - float(prev_week_info['prev_avg_loss']))

                    if calculated_avg_loss == 0:
                        calculated_rsi = 100
                    else:
                        rs = calculated_avg_gain / calculated_avg_loss
                        calculated_rsi = 100 - (100 / (1 + rs))

                    logger.info(f"Manual calculation for weekly RSI:")
                    logger.info(f"  week_change: {week_change}")
                    logger.info(f"  week_gain: {week_gain}")
                    logger.info(f"  week_loss: {week_loss}")
                    logger.info(f"  calculated_avg_gain: {calculated_avg_gain}")
                    logger.info(f"  calculated_avg_loss: {calculated_avg_loss}")
                    logger.info(f"  calculated_RSI: {calculated_rsi}")
                    logger.info(f"  stored avg_gain: {weekly_info['current_avg_gain']}")
                    logger.info(f"  stored avg_loss: {weekly_info['current_avg_loss']}")

                    # Now check what the sliding window is doing
                    daily_999_info = await conn.fetchrow("""
                        SELECT
                            weekly_close,
                            indicators->>'weekly_rsi_14' as sliding_rsi
                        FROM daily_candles
                        WHERE symbol = $1 AND candle_sequence_number = 999
                    """, test_symbol)

                    logger.info(f"Daily 999 sliding window:")
                    logger.info(f"  weekly_close: {daily_999_info['weekly_close']}")
                    logger.info(f"  sliding_rsi: {daily_999_info['sliding_rsi']}")

                    # Manual sliding window calculation
                    sliding_week_change = float(daily_999_info['weekly_close']) - float(prev_week_info['prev_week_close'])
                    sliding_week_gain = max(sliding_week_change, 0)
                    sliding_week_loss = max(-sliding_week_change, 0)

                    sliding_avg_gain = float(prev_week_info['prev_avg_gain']) + alpha * (sliding_week_gain - float(prev_week_info['prev_avg_gain']))
                    sliding_avg_loss = float(prev_week_info['prev_avg_loss']) + alpha * (sliding_week_loss - float(prev_week_info['prev_avg_loss']))

                    if sliding_avg_loss == 0:
                        sliding_rsi = 100
                    else:
                        sliding_rs = sliding_avg_gain / sliding_avg_loss
                        sliding_rsi = 100 - (100 / (1 + sliding_rs))

                    logger.info(f"Manual sliding window calculation:")
                    logger.info(f"  sliding_week_change: {sliding_week_change}")
                    logger.info(f"  sliding_week_gain: {sliding_week_gain}")
                    logger.info(f"  sliding_week_loss: {sliding_week_loss}")
                    logger.info(f"  sliding_avg_gain: {sliding_avg_gain}")
                    logger.info(f"  sliding_avg_loss: {sliding_avg_loss}")
                    logger.info(f"  sliding_RSI: {sliding_rsi}")

            await conn.close()

        except Exception as e:
            logger.error(f"Debug failed: {e}")

async def main():
    debugger = DetailedRSIDebugger()
    await debugger.debug_detailed_calculation()

if __name__ == "__main__":
    asyncio.run(main())