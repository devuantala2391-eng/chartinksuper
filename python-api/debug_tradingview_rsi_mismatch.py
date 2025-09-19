"""
Debug RSI discrepancy with TradingView
Investigate why our RSI (58.17) differs from TradingView RSI (58.06)
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingViewRSIDebugger:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def debug_tradingview_rsi_mismatch(self):
        """Debug the RSI mismatch with TradingView"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Debugging TradingView RSI mismatch for symbol: {test_symbol}")
            logger.info("Our RSI: 58.17, TradingView RSI: 58.06 (difference: 0.11)")

            # Get the latest monthly candle data
            latest_monthly = await conn.fetchrow("""
                SELECT
                    month_sequence_number,
                    open,
                    high,
                    low,
                    close,
                    indicators->>'monthly_rsi_14' as our_rsi,
                    indicators->>'_monthly_rsi_14_avg_gain' as avg_gain,
                    indicators->>'_monthly_rsi_14_avg_loss' as avg_loss
                FROM monthly_candles
                WHERE symbol = $1
                ORDER BY month_sequence_number DESC
                LIMIT 1
            """, test_symbol)

            logger.info(f"Latest monthly candle (Month {latest_monthly['month_sequence_number']}):")
            logger.info(f"  OHLC: O={latest_monthly['open']}, H={latest_monthly['high']}, L={latest_monthly['low']}, C={latest_monthly['close']}")
            logger.info(f"  Our RSI: {latest_monthly['our_rsi']}")
            logger.info(f"  Avg Gain: {latest_monthly['avg_gain']}, Avg Loss: {latest_monthly['avg_loss']}")

            # Check how many monthly candles we have (data sufficiency)
            total_monthly_candles = await conn.fetchval("""
                SELECT COUNT(*)
                FROM monthly_candles
                WHERE symbol = $1
                AND indicators->>'monthly_rsi_14' IS NOT NULL
            """, test_symbol)

            logger.info(f"Total monthly candles with RSI: {total_monthly_candles}")

            # Check the calculation history for the latest month
            logger.info("\n--- RSI Calculation History (Last 15 months) ---")
            rsi_history = await conn.fetch("""
                SELECT
                    month_sequence_number,
                    close,
                    LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close,
                    close - LAG(close, 1) OVER (ORDER BY month_sequence_number) as month_change,
                    indicators->>'monthly_rsi_14' as rsi
                FROM monthly_candles
                WHERE symbol = $1
                AND month_sequence_number >= $2 - 15
                ORDER BY month_sequence_number
            """, test_symbol, latest_monthly['month_sequence_number'])

            for record in rsi_history:
                change = record['month_change'] if record['month_change'] is not None else 0
                gain = max(change, 0) if change is not None else 0
                loss = max(-change, 0) if change is not None else 0

                logger.info(f"Month {record['month_sequence_number']}: close={record['close']}, change={change:.2f}, gain={gain:.2f}, loss={loss:.2f}, RSI={record['rsi']}")

            # Manual RSI calculation for verification
            logger.info("\n--- Manual RSI Calculation Verification ---")

            # Get the last 14+ months for manual calculation
            manual_calc_data = await conn.fetch("""
                SELECT
                    month_sequence_number,
                    close,
                    LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close
                FROM monthly_candles
                WHERE symbol = $1
                AND month_sequence_number >= $2 - 20
                ORDER BY month_sequence_number
            """, test_symbol, latest_monthly['month_sequence_number'])

            if len(manual_calc_data) >= 15:  # Need at least 15 for 14-period RSI
                gains = []
                losses = []

                for i in range(1, len(manual_calc_data)):  # Skip first record (no previous close)
                    change = float(manual_calc_data[i]['close']) - float(manual_calc_data[i]['prev_close'])
                    gain = max(change, 0)
                    loss = max(-change, 0)
                    gains.append(gain)
                    losses.append(loss)

                logger.info(f"Total price changes calculated: {len(gains)}")

                if len(gains) >= 14:
                    # TradingView uses SMA for initial average, then EMA (Wilder's smoothing)
                    initial_avg_gain = sum(gains[:14]) / 14
                    initial_avg_loss = sum(losses[:14]) / 14

                    logger.info(f"Initial 14-period averages (SMA method):")
                    logger.info(f"  Initial avg gain: {initial_avg_gain:.4f}")
                    logger.info(f"  Initial avg loss: {initial_avg_loss:.4f}")

                    # Apply Wilder's smoothing for subsequent periods
                    avg_gain = initial_avg_gain
                    avg_loss = initial_avg_loss
                    alpha = 1.0 / 14

                    for i in range(14, len(gains)):
                        avg_gain = avg_gain * (13/14) + gains[i] * (1/14)  # Wilder's method
                        avg_loss = avg_loss * (13/14) + losses[i] * (1/14)

                    logger.info(f"Final averages after Wilder's smoothing:")
                    logger.info(f"  Final avg gain: {avg_gain:.4f}")
                    logger.info(f"  Final avg loss: {avg_loss:.4f}")

                    # Calculate RSI
                    if avg_loss == 0:
                        manual_rsi = 100
                    else:
                        rs = avg_gain / avg_loss
                        manual_rsi = 100 - (100 / (1 + rs))

                    logger.info(f"Manual RSI calculation result: {manual_rsi:.2f}")
                    logger.info(f"Our stored RSI: {latest_monthly['our_rsi']}")
                    logger.info(f"TradingView RSI: 58.06")
                    logger.info(f"Difference from TradingView: {abs(manual_rsi - 58.06):.2f}")

            # Check if we're missing any data that TradingView might have
            logger.info(f"\n--- Data Completeness Check ---")
            first_candle = await conn.fetchrow("""
                SELECT month_sequence_number
                FROM monthly_candles
                WHERE symbol = $1
                ORDER BY month_sequence_number
                LIMIT 1
            """, test_symbol)

            logger.info(f"Our earliest data: Month {first_candle['month_sequence_number']}")
            logger.info(f"Total months of data: {latest_monthly['month_sequence_number'] - first_candle['month_sequence_number'] + 1}")

            await conn.close()

        except Exception as e:
            logger.error(f"Debug failed: {e}")
            return False

async def main():
    debugger = TradingViewRSIDebugger()
    await debugger.debug_tradingview_rsi_mismatch()

if __name__ == "__main__":
    asyncio.run(main())