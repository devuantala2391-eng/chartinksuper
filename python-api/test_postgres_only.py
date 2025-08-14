"""Test PostgreSQL-only operation (no file fallback)"""

import asyncio
import logging
from services.db_wrapper import db_wrapper
from services.nse_database_service import nse_db_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_postgres_only():
    """Test that the system only uses PostgreSQL without file fallback"""
    try:
        # Initialize database wrapper
        logger.info("Initializing database wrapper...")
        await db_wrapper.initialize()
        
        if not db_wrapper.initialized:
            logger.error("❌ Database wrapper failed to initialize")
            return False
        
        logger.info("✓ Database wrapper initialized (PostgreSQL only)")
        
        # Test saving data
        test_symbol = 'TEST_POSTGRES_ONLY'
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
        
        logger.info(f"Testing save to PostgreSQL for {test_symbol}...")
        success = await db_wrapper.save_candles(test_symbol, test_data)
        
        if not success:
            logger.error("❌ Failed to save to PostgreSQL")
            return False
        
        logger.info("✓ Successfully saved to PostgreSQL")
        
        # Test loading data
        logger.info(f"Testing load from PostgreSQL for {test_symbol}...")
        loaded_data = await db_wrapper.load_candles(test_symbol, limit=1)
        
        if not loaded_data:
            logger.error("❌ Failed to load from PostgreSQL")
            return False
        
        logger.info(f"✓ Successfully loaded {len(loaded_data)} candles from PostgreSQL")
        
        # Test latest candle
        logger.info(f"Testing get latest candle for {test_symbol}...")
        latest = await db_wrapper.get_latest_candle(test_symbol)
        
        if not latest:
            logger.error("❌ Failed to get latest candle from PostgreSQL")
            return False
        
        logger.info(f"✓ Successfully got latest candle: close={latest.get('close')}")
        
        # Verify PostgreSQL is being used
        if not db_wrapper.using_postgres:
            logger.error("❌ System is not using PostgreSQL!")
            return False
        
        logger.info("✓ Confirmed: System is using PostgreSQL only")
        
        # Check that db folder doesn't exist
        from pathlib import Path
        db_path = Path(__file__).parent / "db"
        if db_path.exists():
            logger.warning("⚠️  Warning: db folder still exists (but not being used)")
        else:
            logger.info("✓ db folder has been removed as expected")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False
    finally:
        # Clean up
        if db_wrapper.initialized:
            await db_wrapper.close()
            logger.info("Database connections closed")

async def main():
    """Run the test"""
    logger.info("=" * 60)
    logger.info("TESTING POSTGRESQL-ONLY OPERATION")
    logger.info("=" * 60)
    
    success = await test_postgres_only()
    
    logger.info("=" * 60)
    if success:
        logger.info("✅ ALL TESTS PASSED - PostgreSQL-only mode working correctly")
    else:
        logger.error("❌ TESTS FAILED - Check the logs above")
    logger.info("=" * 60)
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)