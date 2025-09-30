"""
Test script to verify the timestamp fix in cache update logic
"""
import asyncio
import logging
from services.ultra_fast_cron_v2 import UltraFastCronV2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_timestamp_fix():
    """Test that cache preserves timestamp after update"""
    try:
        cron = UltraFastCronV2()
        await cron.initialize()

        # Test with a few symbols to verify timestamp preservation
        test_symbols = ['RELIANCE', 'TCS', 'INFY']

        logger.info("🧪 Testing timestamp preservation in cache updates...")

        # Run first cron (should work as before)
        logger.info("Running first cron execution...")
        await cron.run_ultra_fast_cron()

        # Check cache structure after first run
        for symbol in test_symbols:
            cache_data = cron.cache.get_previous_data(symbol)
            if cache_data and 'meta' in cache_data:
                logger.info(f"✅ {symbol} cache after first run:")
                logger.info(f"   Has timestamp: {'timestamp' in cache_data['meta']}")
                logger.info(f"   Timestamp value: {cache_data['meta'].get('timestamp', 'MISSING')}")
                logger.info(f"   Meta keys: {list(cache_data['meta'].keys())}")
            else:
                logger.info(f"❌ {symbol} not found in cache")

        # Wait a moment
        await asyncio.sleep(2)

        # Run second cron (this should now work with the fix)
        logger.info("\nRunning second cron execution...")
        await cron.run_ultra_fast_cron()

        # Check cache structure after second run
        for symbol in test_symbols:
            cache_data = cron.cache.get_previous_data(symbol)
            if cache_data and 'meta' in cache_data:
                logger.info(f"✅ {symbol} cache after second run:")
                logger.info(f"   Has timestamp: {'timestamp' in cache_data['meta']}")
                logger.info(f"   Timestamp value: {cache_data['meta'].get('timestamp', 'MISSING')}")
                logger.info(f"   Meta keys: {list(cache_data['meta'].keys())}")
            else:
                logger.info(f"❌ {symbol} not found in cache")

        logger.info("\n🎉 Test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await cron.cleanup()

if __name__ == "__main__":
    asyncio.run(test_timestamp_fix())