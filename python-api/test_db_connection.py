"""Test database connection with improved pool settings"""

import asyncio
import logging
from services.nse_database_service import nse_db_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_connection():
    """Test database connection and pool health"""
    try:
        # Initialize database
        logger.info("Initializing database...")
        await nse_db_service.initialize()
        
        if not nse_db_service.initialized:
            logger.error("Database initialization failed")
            return False
        
        logger.info("Database initialized successfully")
        
        # Test health check
        logger.info("Running health check...")
        is_healthy = await nse_db_service.health_check()
        logger.info(f"Health check result: {is_healthy}")
        
        if not is_healthy:
            logger.error("Database health check failed")
            return False
        
        # Test saving data
        logger.info("Testing data save...")
        test_data = [
            {
                'timestamp': 1234567890,
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 103.0,
                'volume': 10000
            }
        ]
        
        success = await nse_db_service.save_candles('TEST_SYMBOL', test_data)
        logger.info(f"Save test result: {success}")
        
        if not success:
            logger.error("Failed to save test data")
            return False
        
        # Test loading data
        logger.info("Testing data load...")
        loaded_data = await nse_db_service.load_candles('TEST_SYMBOL', limit=1)
        
        if loaded_data:
            logger.info(f"Successfully loaded {len(loaded_data)} candles")
        else:
            logger.warning("No data loaded")
        
        # Test concurrent connections
        logger.info("Testing concurrent connections...")
        tasks = []
        for i in range(5):
            tasks.append(nse_db_service.health_check())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures = sum(1 for r in results if isinstance(r, Exception) or not r)
        
        if failures > 0:
            logger.warning(f"{failures} out of 5 concurrent connections failed")
        else:
            logger.info("All concurrent connections succeeded")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False
    finally:
        # Close connections
        if nse_db_service.initialized:
            await nse_db_service.close()
            logger.info("Database connections closed")

async def main():
    """Run the test"""
    success = await test_connection()
    if success:
        logger.info("✓ Database connection test PASSED")
    else:
        logger.error("✗ Database connection test FAILED")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)