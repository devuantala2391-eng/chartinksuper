"""
Verify RSI calculation method by tracing the exact calculation steps
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RSICalculationMethodVerifier:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def verify_rsi_calculation_method(self):
        """Verify the exact RSI calculation method being used"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Verifying RSI calculation method for symbol: {test_symbol}")

            # Get raw monthly data to trace exact calculation
            monthly_data = await conn.fetch("""
                SELECT
                    month_sequence_number,
                    close,
                    LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close,
                    indicators->>'monthly_rsi_14' as stored_rsi
                FROM monthly_candles
                WHERE symbol = $1
                AND month_sequence_number >= 28  -- Get enough data for calculation
                ORDER BY month_sequence_number
            """, test_symbol)

            logger.info("Raw monthly data and price changes:")
            gains = []
            losses = []

            for i, record in enumerate(monthly_data):
                if record['prev_close'] is not None:
                    change = float(record['close']) - float(record['prev_close'])
                    gain = max(change, 0)
                    loss = max(-change, 0)
                    gains.append(gain)
                    losses.append(loss)

                    logger.info(f"Month {record['month_sequence_number']}: {record['prev_close']:.2f} -> {record['close']:.2f}, change={change:.2f}, gain={gain:.2f}, loss={loss:.2f}, stored_rsi={record['stored_rsi']}")

            if len(gains) >= 14:
                logger.info(f"\n--- Step-by-Step RSI Calculation ---")

                # Method 1: TradingView/Standard method (SMA for first period, then EMA)
                logger.info("Method 1: Standard TradingView method")
                initial_avg_gain = sum(gains[:14]) / 14
                initial_avg_loss = sum(losses[:14]) / 14

                logger.info(f"Initial 14-period SMA: gain={initial_avg_gain:.4f}, loss={initial_avg_loss:.4f}")

                current_avg_gain = initial_avg_gain
                current_avg_loss = initial_avg_loss

                # Calculate RSI for each subsequent period
                for i in range(14, len(gains)):
                    # Wilder's smoothing (EMA with alpha = 1/14)
                    current_avg_gain = (current_avg_gain * 13 + gains[i]) / 14
                    current_avg_loss = (current_avg_loss * 13 + losses[i]) / 14

                    if current_avg_loss == 0:
                        rsi = 100
                    else:
                        rs = current_avg_gain / current_avg_loss
                        rsi = 100 - (100 / (1 + rs))

                    month_num = i + 1 + 28  # Adjust for our starting month
                    stored_rsi = None
                    for record in monthly_data:
                        if record['month_sequence_number'] == month_num:
                            stored_rsi = record['stored_rsi']
                            break

                    logger.info(f"  Month {month_num}: avg_gain={current_avg_gain:.4f}, avg_loss={current_avg_loss:.4f}, calculated_rsi={rsi:.2f}, stored_rsi={stored_rsi}")

                # Method 2: Check if we're using pure EMA approach (different initial calculation)
                logger.info(f"\nMethod 2: Pure EMA approach (what our DB might be doing)")

                # Start with first period values instead of SMA
                ema_avg_gain = gains[0]
                ema_avg_loss = losses[0]
                alpha = 1.0 / 14

                for i in range(1, len(gains)):
                    ema_avg_gain = ema_avg_gain + alpha * (gains[i] - ema_avg_gain)
                    ema_avg_loss = ema_avg_loss + alpha * (losses[i] - ema_avg_loss)

                    if i >= 13:  # Only show RSI after 14 periods
                        if ema_avg_loss == 0:
                            rsi = 100
                        else:
                            rs = ema_avg_gain / ema_avg_loss
                            rsi = 100 - (100 / (1 + rs))

                        month_num = i + 1 + 28
                        if month_num <= 48:  # Only show up to latest month
                            logger.info(f"  Month {month_num}: EMA_gain={ema_avg_gain:.4f}, EMA_loss={ema_avg_loss:.4f}, calculated_rsi={rsi:.2f}")

            # Check what our stored intermediate values show
            logger.info(f"\n--- Our Stored Intermediate Values ---")
            latest_stored = await conn.fetchrow("""
                SELECT
                    indicators->>'monthly_rsi_14' as rsi,
                    indicators->>'_monthly_rsi_14_avg_gain' as avg_gain,
                    indicators->>'_monthly_rsi_14_avg_loss' as avg_loss
                FROM monthly_candles
                WHERE symbol = $1
                ORDER BY month_sequence_number DESC
                LIMIT 1
            """, test_symbol)

            logger.info(f"Latest stored values:")
            logger.info(f"  RSI: {latest_stored['rsi']}")
            logger.info(f"  Avg Gain: {latest_stored['avg_gain']}")
            logger.info(f"  Avg Loss: {latest_stored['avg_loss']}")

            # Manual verification of stored values
            if latest_stored['avg_gain'] and latest_stored['avg_loss']:
                stored_gain = float(latest_stored['avg_gain'])
                stored_loss = float(latest_stored['avg_loss'])

                manual_rs = stored_gain / stored_loss
                manual_rsi = 100 - (100 / (1 + manual_rs))

                logger.info(f"Manual RSI from stored averages: {manual_rsi:.2f}")
                logger.info(f"Difference from stored RSI: {abs(manual_rsi - float(latest_stored['rsi'])):.2f}")

            await conn.close()

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

async def main():
    verifier = RSICalculationMethodVerifier()
    await verifier.verify_rsi_calculation_method()

if __name__ == "__main__":
    asyncio.run(main())