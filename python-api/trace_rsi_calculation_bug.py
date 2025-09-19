"""
Trace the RSI calculation step by step to find the exact bug
"""
import asyncio
import asyncpg
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RSICalculationTracer:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }

    async def trace_rsi_calculation_bug(self):
        """Trace the RSI calculation step by step to find the bug"""
        try:
            conn = await asyncpg.connect(**self.db_config)

            test_symbol = '20MICRONS'

            logger.info(f"Tracing RSI calculation bug for symbol: {test_symbol}")

            # Clear one specific monthly candle and recalculate just that one to trace
            latest_month = await conn.fetchval("""
                SELECT MAX(month_sequence_number)
                FROM monthly_candles
                WHERE symbol = $1
            """, test_symbol)

            logger.info(f"Tracing calculation for latest month: {latest_month}")

            # Clear just the latest month's RSI
            await conn.execute("""
                UPDATE monthly_candles
                SET indicators = indicators - 'monthly_rsi_14' - '_monthly_rsi_14_avg_gain' - '_monthly_rsi_14_avg_loss'
                WHERE symbol = $1 AND month_sequence_number = $2
            """, test_symbol, latest_month)

            # Check what initial SMA calculation should be for month 42 (first RSI calculation)
            logger.info("Checking initial SMA calculation for month 42...")
            initial_sma_data = await conn.fetch("""
                SELECT
                    month_sequence_number,
                    close,
                    LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close,
                    close - LAG(close, 1) OVER (ORDER BY month_sequence_number) as change
                FROM monthly_candles
                WHERE symbol = $1
                AND month_sequence_number BETWEEN 29 AND 42  -- First 14 periods for month 42
                ORDER BY month_sequence_number
            """, test_symbol)

            gains_sma = []
            losses_sma = []
            logger.info("First 14 periods for SMA (months 29-42):")
            for i, record in enumerate(initial_sma_data):
                if record['change'] is not None:
                    gain = max(record['change'], 0)
                    loss = max(-record['change'], 0)
                    gains_sma.append(gain)
                    losses_sma.append(loss)
                    logger.info(f"  Period {i+1} (Month {record['month_sequence_number']}): {record['prev_close']:.2f} -> {record['close']:.2f}, change={record['change']:.2f}, gain={gain:.2f}, loss={loss:.2f}")

            if len(gains_sma) == 14:
                initial_avg_gain = sum(gains_sma) / 14
                initial_avg_loss = sum(losses_sma) / 14
                logger.info(f"Initial SMA averages: gain={initial_avg_gain:.6f}, loss={initial_avg_loss:.6f}")

                # Now check what our database function actually calculates for month 42
                logger.info("Checking our database function calculation for month 42...")

                # Get the current state for month 41 (previous month)
                month_41_state = await conn.fetchrow("""
                    SELECT
                        indicators->>'monthly_rsi_14' as rsi,
                        indicators->>'_monthly_rsi_14_avg_gain' as avg_gain,
                        indicators->>'_monthly_rsi_14_avg_loss' as avg_loss
                    FROM monthly_candles
                    WHERE symbol = $1 AND month_sequence_number = 41
                """, test_symbol)

                logger.info(f"Month 41 state: RSI={month_41_state['rsi']}, avg_gain={month_41_state['avg_gain']}, avg_loss={month_41_state['avg_loss']}")

                # Force recalculate just month 42 to see what our function does
                logger.info("Manually stepping through our function logic for month 42...")

                # Get month 42 data
                month_42_data = await conn.fetchrow("""
                    SELECT
                        month_sequence_number,
                        close,
                        LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close
                    FROM monthly_candles
                    WHERE symbol = $1 AND month_sequence_number = 42
                """, test_symbol)

                # Calculate the change for month 42
                month_42_change = float(month_42_data['close']) - float(month_42_data['prev_close'])
                month_42_gain = max(month_42_change, 0)
                month_42_loss = max(-month_42_change, 0)

                logger.info(f"Month 42: {month_42_data['prev_close']:.2f} -> {month_42_data['close']:.2f}, change={month_42_change:.2f}")
                logger.info(f"Month 42: gain={month_42_gain:.2f}, loss={month_42_loss:.2f}")

                # Check what our CTE should calculate for the initial SMA for month 42
                logger.info("Testing our CTE logic for month 42 initial SMA...")
                cte_result = await conn.fetchrow("""
                    WITH price_changes AS (
                        SELECT
                            m.close - COALESCE(LAG(m.close, 1) OVER (ORDER BY m.month_sequence_number), m.close) as price_change
                        FROM monthly_candles m
                        WHERE m.symbol = $1
                        AND m.month_sequence_number <= 42
                        AND m.month_sequence_number > 42 - 14
                    )
                    SELECT
                        AVG(GREATEST(price_change, 0)) as avg_gain,
                        AVG(GREATEST(-price_change, 0)) as avg_loss
                    FROM price_changes
                    WHERE price_change IS NOT NULL
                """, test_symbol)

                logger.info(f"Our CTE result for month 42: avg_gain={cte_result['avg_gain']:.6f}, avg_loss={cte_result['avg_loss']:.6f}")
                logger.info(f"Expected manual result: avg_gain={initial_avg_gain:.6f}, avg_loss={initial_avg_loss:.6f}")
                logger.info(f"CTE vs Manual difference: gain={abs(float(cte_result['avg_gain']) - initial_avg_gain):.6f}, loss={abs(float(cte_result['avg_loss']) - initial_avg_loss):.6f}")

            await conn.close()

        except Exception as e:
            logger.error(f"Trace failed: {e}")
            return False

async def main():
    tracer = RSICalculationTracer()
    await tracer.trace_rsi_calculation_bug()

if __name__ == "__main__":
    asyncio.run(main())