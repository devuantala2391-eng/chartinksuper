"""
Compare our RSI calculation with TradingView's exact methodology
Check for data differences that might explain the 0.11 discrepancy
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExactTradingViewComparison:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def compare_with_tradingview_exact(self):
        """Compare our calculation with TradingView's exact methodology"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Exact TradingView comparison for symbol: {test_symbol}")

            # Get the exact 14 months that should be used for initial SMA
            # Starting from month 48 (latest), go back 14 periods for initial calculation
            latest_month = await conn.fetchval("""
                SELECT MAX(month_sequence_number)
                FROM monthly_candles
                WHERE symbol = $1
            """, test_symbol)

            logger.info(f"Latest month: {latest_month}")

            # Get the exact data for RSI calculation
            rsi_calc_data = await conn.fetch("""
                SELECT
                    month_sequence_number,
                    close,
                    LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close
                FROM monthly_candles
                WHERE symbol = $1
                AND month_sequence_number >= $2 - 20  -- Get enough history
                ORDER BY month_sequence_number
            """, test_symbol, latest_month)

            logger.info(f"Retrieved {len(rsi_calc_data)} months of data")

            # Extract gains and losses
            gains = []
            losses = []
            logger.info("\nPrice changes:")

            for i in range(1, len(rsi_calc_data)):  # Skip first (no previous close)
                current = rsi_calc_data[i]
                change = float(current['close']) - float(current['prev_close'])
                gain = max(change, 0)
                loss = max(-change, 0)
                gains.append(gain)
                losses.append(loss)

                logger.info(f"Month {current['month_sequence_number']}: {current['prev_close']:.2f} -> {current['close']:.2f}, change={change:.2f}")

            if len(gains) >= 14:
                # TradingView method: SMA for first 14, then EMA
                logger.info(f"\n--- Exact TradingView Calculation ---")

                # Initial 14-period SMA
                initial_avg_gain = sum(gains[:14]) / 14
                initial_avg_loss = sum(losses[:14]) / 14

                logger.info(f"First 14 periods for SMA calculation:")
                for i in range(14):
                    month_num = rsi_calc_data[i+1]['month_sequence_number']
                    logger.info(f"  Period {i+1} (Month {month_num}): gain={gains[i]:.2f}, loss={losses[i]:.2f}")

                logger.info(f"Initial SMA averages: gain={initial_avg_gain:.6f}, loss={initial_avg_loss:.6f}")

                # Apply Wilder's smoothing for remaining periods
                avg_gain = initial_avg_gain
                avg_loss = initial_avg_loss

                for i in range(14, len(gains)):
                    # Wilder's smoothing: avg = (prev_avg * (n-1) + current_value) / n
                    avg_gain = (avg_gain * 13 + gains[i]) / 14
                    avg_loss = (avg_loss * 13 + losses[i]) / 14

                logger.info(f"\nFinal values after Wilder's smoothing:")
                logger.info(f"Final avg_gain: {avg_gain:.6f}")
                logger.info(f"Final avg_loss: {avg_loss:.6f}")

                # Calculate final RSI
                if avg_loss == 0:
                    calculated_rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    calculated_rsi = 100 - (100 / (1 + rs))

                logger.info(f"Calculated RSI: {calculated_rsi:.6f}")
                logger.info(f"Rounded RSI: {round(calculated_rsi, 2)}")

                # Compare with our stored values
                our_stored = await conn.fetchrow("""
                    SELECT
                        indicators->>'monthly_rsi_14' as rsi,
                        indicators->>'_monthly_rsi_14_avg_gain' as avg_gain,
                        indicators->>'_monthly_rsi_14_avg_loss' as avg_loss
                    FROM monthly_candles
                    WHERE symbol = $1
                    ORDER BY month_sequence_number DESC
                    LIMIT 1
                """, test_symbol)

                logger.info(f"\n--- Comparison ---")
                logger.info(f"Manual calculation: {calculated_rsi:.2f}")
                logger.info(f"Our stored RSI: {our_stored['rsi']}")
                logger.info(f"TradingView RSI: 58.06")
                logger.info(f"Our stored avg_gain: {our_stored['avg_gain']}")
                logger.info(f"Manual avg_gain: {avg_gain:.4f}")
                logger.info(f"Our stored avg_loss: {our_stored['avg_loss']}")
                logger.info(f"Manual avg_loss: {avg_loss:.4f}")

                # Check if the discrepancy is in rounding or precision
                logger.info(f"\n--- Precision Analysis ---")
                logger.info(f"Manual vs Stored RSI difference: {abs(calculated_rsi - float(our_stored['rsi'])):.4f}")
                logger.info(f"Manual vs TradingView difference: {abs(calculated_rsi - 58.06):.4f}")
                logger.info(f"Stored vs TradingView difference: {abs(float(our_stored['rsi']) - 58.06):.4f}")

                # Check if there's a small data difference
                logger.info(f"\n--- Data Validation ---")
                logger.info(f"Latest close price in our data: {rsi_calc_data[-1]['close']}")
                logger.info(f"Previous close price: {rsi_calc_data[-1]['prev_close']}")
                logger.info(f"Latest change: {float(rsi_calc_data[-1]['close']) - float(rsi_calc_data[-1]['prev_close']):.2f}")

            await conn.close()

        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            return False

async def main():
    comparator = ExactTradingViewComparison()
    await comparator.compare_with_tradingview_exact()

if __name__ == "__main__":
    asyncio.run(main())