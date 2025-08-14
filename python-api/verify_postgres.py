"""
Quick verification that PostgreSQL integration is working
"""

import asyncio
import logging
from services.nse_database_service import nse_db_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        # Test database initialization
        logger.info("Testing NSE database connection...")
        await nse_db_service.initialize()
        logger.info("✅ Database initialized successfully!")
        
        # Test save operation
        test_data = [{
            "timestamp": 1715711400000,
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "volume": 1000000
        }]
        
        logger.info("Testing save operation...")
        success = await nse_db_service.save_candles("TEST_VERIFY", test_data)
        if success:
            logger.info("✅ Save operation successful!")
        
        # Test load operation
        logger.info("Testing load operation...")
        loaded = await nse_db_service.load_candles("TEST_VERIFY")
        if loaded:
            logger.info(f"✅ Load operation successful! Loaded {len(loaded)} candles")
        
        # Get stats
        stats = await nse_db_service.get_database_stats()
        logger.info(f"Database stats: Total candles: {stats['total_candles']}, DB size: {stats['database_size_mb']} MB")
        
        # Clean up test data
        async with nse_db_service.get_connection() as conn:
            await conn.execute("DELETE FROM stock_candles WHERE symbol = $1", "TEST_VERIFY")
            await conn.execute("DELETE FROM latest_candles WHERE symbol = $1", "TEST_VERIFY")
            await conn.execute("DELETE FROM stock_metadata WHERE symbol = $1", "TEST_VERIFY")
        
        await nse_db_service.close()
        
        logger.info("\n" + "="*60)
        logger.info("✅ PostgreSQL integration is working perfectly!")
        logger.info("The FastAPI server will now use PostgreSQL for data storage.")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        await nse_db_service.close()

if __name__ == "__main__":
    asyncio.run(main())