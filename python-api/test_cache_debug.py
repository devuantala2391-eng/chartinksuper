"""
Debug script to check cache loading and database data
"""
import asyncio
import logging
from services.ultra_fast_database_service import ultra_fast_db
from services.ultra_fast_cron_v2 import PreviousDayCache
from datetime import date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_cache():
    """Debug the cache loading issue"""
    try:
        # Initialize database
        await ultra_fast_db.initialize()

        # Check symbol_latest_keys table
        async with ultra_fast_db.pool.acquire() as conn:
            # Check if we have any data in symbol_latest_keys
            count = await conn.fetchval("SELECT COUNT(*) FROM symbol_latest_keys")
            logger.info(f"Total symbols in symbol_latest_keys: {count}")

            # Check a few symbols
            sample_symbols = await conn.fetch("""
                SELECT symbol, latest_daily_key, latest_weekly_key, latest_monthly_key
                FROM symbol_latest_keys
                LIMIT 10
            """)

            logger.info("Sample symbols with their latest keys:")
            for row in sample_symbols:
                logger.info(f"  {row['symbol']}: daily={row['latest_daily_key']}, weekly={row['latest_weekly_key']}, monthly={row['latest_monthly_key']}")

            # Check if we have daily_candles data
            candle_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
            logger.info(f"Total candles in daily_candles: {candle_count}")

            # Check a specific symbol's data
            test_symbol = 'RELIANCE'
            symbol_data = await conn.fetch("""
                SELECT candle_key_id, candle_sequence_number, timestamp, open, high, low, close
                FROM daily_candles
                WHERE symbol = $1
                ORDER BY candle_sequence_number DESC
                LIMIT 5
            """, test_symbol)

            logger.info(f"\nLast 5 candles for {test_symbol}:")
            for candle in symbol_data:
                logger.info(f"  Key: {candle['candle_key_id']}, Seq: {candle['candle_sequence_number']}, OHLC: {candle['open']}/{candle['high']}/{candle['low']}/{candle['close']}")

            # Now test the cache loading
            logger.info("\nTesting cache loading...")
            cache = PreviousDayCache()
            success = await cache.load_cache()

            if success:
                logger.info(f"Cache loaded successfully with {len(cache.cache_data)} symbols")

                # Check if RELIANCE is in cache
                reliance_cache = cache.get_previous_data('RELIANCE')
                if reliance_cache:
                    logger.info(f"RELIANCE cache data found:")
                    logger.info(f"  Daily: {reliance_cache['daily']}")
                    logger.info(f"  Meta: {reliance_cache['meta']}")
                else:
                    logger.info("RELIANCE not found in cache")

                # Check first 5 symbols in cache
                if cache.cache_data:
                    logger.info("\nFirst 5 symbols in cache:")
                    for symbol in list(cache.cache_data.keys())[:5]:
                        logger.info(f"  {symbol}: {cache.cache_data[symbol]['daily']}")
            else:
                logger.info("Cache loading failed")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(debug_cache())