"""
Debug script to investigate duplicate candle creation issue
"""
import asyncio
import logging
from services.ultra_fast_database_service import ultra_fast_db
from datetime import datetime, date, timezone
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_duplicate_candles():
    """Debug the duplicate candle creation issue"""
    try:
        # Initialize database
        await ultra_fast_db.initialize()

        symbol = 'MIDQ50ADD'

        async with ultra_fast_db.pool.acquire() as conn:
            # Get candles 95-110 for the symbol
            candles = await conn.fetch("""
                SELECT
                    candle_sequence_number,
                    candle_key_id,
                    timestamp,
                    open, high, low, close, volume,
                    created_at,
                    updated_at,
                    DATE(to_timestamp(timestamp / 1000.0) AT TIME ZONE 'Asia/Kolkata') as date_ist,
                    DATE(to_timestamp(timestamp / 1000.0)) as date_utc
                FROM daily_candles
                WHERE symbol = $1
                AND candle_sequence_number BETWEEN 95 AND 110
                ORDER BY candle_sequence_number ASC
            """, symbol)

            logger.info(f"\nCandles for {symbol} (sequence 95-110):")
            logger.info("=" * 100)

            prev_date_ist = None
            prev_date_utc = None

            for candle in candles:
                seq = candle['candle_sequence_number']
                key = candle['candle_key_id']
                ts = candle['timestamp']
                date_ist = candle['date_ist']
                date_utc = candle['date_utc']
                created = candle['created_at']
                updated = candle['updated_at']

                # Check if this is a duplicate (same date as previous)
                is_duplicate = ""
                if prev_date_ist and prev_date_ist == date_ist:
                    is_duplicate = " [DUPLICATE - SAME DATE AS PREVIOUS!]"

                logger.info(f"Seq #{seq}: Key={key}")
                logger.info(f"  Timestamp: {ts}")
                logger.info(f"  Date IST: {date_ist}, Date UTC: {date_utc}{is_duplicate}")
                logger.info(f"  OHLCV: {candle['open']}/{candle['high']}/{candle['low']}/{candle['close']}, Vol={candle['volume']}")
                logger.info(f"  Created: {created}, Updated: {updated}")
                logger.info("-" * 50)

                prev_date_ist = date_ist
                prev_date_utc = date_utc

            # Now let's check the cache date comparison logic
            logger.info("\n" + "=" * 100)
            logger.info("CHECKING CACHE DATE COMPARISON LOGIC:")
            logger.info("=" * 100)

            # Get the latest candle
            latest_candle = await conn.fetchrow("""
                SELECT
                    candle_key_id,
                    timestamp,
                    DATE(to_timestamp(timestamp / 1000.0) AT TIME ZONE 'Asia/Kolkata') as date_ist,
                    DATE(to_timestamp(timestamp / 1000.0)) as date_utc
                FROM daily_candles
                WHERE symbol = $1
                ORDER BY candle_sequence_number DESC
                LIMIT 1
            """, symbol)

            if latest_candle:
                logger.info(f"\nLatest candle for {symbol}:")
                logger.info(f"  Key: {latest_candle['candle_key_id']}")
                logger.info(f"  Timestamp: {latest_candle['timestamp']}")
                logger.info(f"  Date IST: {latest_candle['date_ist']}")
                logger.info(f"  Date UTC: {latest_candle['date_utc']}")

                # Check what today's date is in different timezones
                now = datetime.now()
                today_local = now.date()
                today_utc = datetime.now(timezone.utc).date()
                ist = pytz.timezone('Asia/Kolkata')
                today_ist = datetime.now(ist).date()

                logger.info(f"\nToday's date comparison:")
                logger.info(f"  Local date: {today_local}")
                logger.info(f"  UTC date: {today_utc}")
                logger.info(f"  IST date: {today_ist}")
                logger.info(f"  Latest candle IST date: {latest_candle['date_ist']}")

                if latest_candle['date_ist'] == today_ist:
                    logger.info("  -> Latest candle is from TODAY (IST) - should UPDATE")
                else:
                    logger.info("  -> Latest candle is from PREVIOUS day - should CREATE NEW")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(debug_duplicate_candles())