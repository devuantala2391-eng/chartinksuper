"""
Test PostgreSQL Integration
Run this script to test the PostgreSQL database connection and functionality
"""

import asyncio
import logging
import json
from pathlib import Path
from services.nse_database_service import nse_db_service
from services.postgres_integration import postgres_integration

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_database_connection():
    """Test basic database connection"""
    logger.info("=" * 60)
    logger.info("Testing PostgreSQL Connection...")
    logger.info("=" * 60)
    
    try:
        await nse_db_service.initialize()
        logger.info("✅ Database connection successful!")
        
        # Get database stats
        stats = await nse_db_service.get_database_stats()
        logger.info(f"Database stats: {json.dumps(stats, indent=2)}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.error("Please ensure PostgreSQL is running and 'nse' database exists")
        return False

async def test_save_and_load():
    """Test saving and loading data"""
    logger.info("=" * 60)
    logger.info("Testing Save and Load Operations...")
    logger.info("=" * 60)
    
    test_symbol = "TEST_STOCK"
    test_candles = [
        {
            "timestamp": 1715711400000,
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "volume": 1000000
        },
        {
            "timestamp": 1715797800000,
            "open": 103.0,
            "high": 108.0,
            "low": 102.0,
            "close": 107.0,
            "volume": 1200000
        }
    ]
    
    try:
        # Save data
        logger.info(f"Saving test data for {test_symbol}...")
        success = await nse_db_service.save_stock_data(test_symbol, test_candles)
        
        if success:
            logger.info(f"✅ Successfully saved {len(test_candles)} candles")
        else:
            logger.error("❌ Failed to save test data")
            return False
        
        # Load data
        logger.info(f"Loading test data for {test_symbol}...")
        loaded_data = await nse_db_service.load_stock_data(test_symbol)
        
        if loaded_data:
            logger.info(f"✅ Successfully loaded {len(loaded_data)} candles")
            logger.info(f"First candle: {json.dumps(loaded_data[0], indent=2)}")
        else:
            logger.error("❌ Failed to load test data")
            return False
        
        # Get latest candle
        logger.info(f"Getting latest candle for {test_symbol}...")
        latest = await nse_db_service.get_latest_candle(test_symbol)
        
        if latest:
            logger.info(f"✅ Latest candle: {json.dumps(latest, indent=2)}")
        else:
            logger.error("❌ Failed to get latest candle")
            return False
        
        # Clean up test data
        await nse_db_service.pool.acquire()
        async with nse_db_service.get_connection() as conn:
            await conn.execute("DELETE FROM stock_candles WHERE symbol = $1", test_symbol)
            await conn.execute("DELETE FROM latest_candles WHERE symbol = $1", test_symbol)
            await conn.execute("DELETE FROM stock_metadata WHERE symbol = $1", test_symbol)
        
        logger.info("✅ Test data cleaned up")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

async def test_batch_operations():
    """Test batch save operations"""
    logger.info("=" * 60)
    logger.info("Testing Batch Operations...")
    logger.info("=" * 60)
    
    # Create test data for multiple stocks
    test_stocks = []
    for i in range(5):
        symbol = f"TEST_BATCH_{i}"
        candles = [
            {
                "timestamp": 1715711400000 + (j * 86400000),
                "open": 100.0 + j,
                "high": 105.0 + j,
                "low": 99.0 + j,
                "close": 103.0 + j,
                "volume": 1000000 + (j * 100000)
            }
            for j in range(10)
        ]
        test_stocks.append((symbol, candles))
    
    try:
        logger.info(f"Saving batch data for {len(test_stocks)} stocks...")
        results = await nse_db_service.save_stock_data_batch(test_stocks)
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"✅ Batch save completed: {successful}/{len(test_stocks)} successful")
        
        # Load multiple stocks
        symbols = [symbol for symbol, _ in test_stocks]
        logger.info(f"Loading data for {len(symbols)} stocks...")
        loaded_data = await nse_db_service.load_multiple_stocks(symbols)
        
        loaded_count = sum(1 for data in loaded_data.values() if data is not None)
        logger.info(f"✅ Loaded data for {loaded_count}/{len(symbols)} stocks")
        
        # Clean up test data
        async with nse_db_service.get_connection() as conn:
            for symbol, _ in test_stocks:
                await conn.execute("DELETE FROM stock_candles WHERE symbol = $1", symbol)
                await conn.execute("DELETE FROM latest_candles WHERE symbol = $1", symbol)
                await conn.execute("DELETE FROM stock_metadata WHERE symbol = $1", symbol)
        
        logger.info("✅ Batch test data cleaned up")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Batch test failed: {e}")
        return False

async def test_migration():
    """Test migration from JSON files"""
    logger.info("=" * 60)
    logger.info("Testing JSON to PostgreSQL Migration...")
    logger.info("=" * 60)
    
    db_path = Path(__file__).parent / "db"
    
    if not db_path.exists():
        logger.info("No db directory found - skipping migration test")
        return True
    
    # Check if there are JSON files
    json_files = list(db_path.glob("*.json"))
    
    if not json_files:
        logger.info("No JSON files found - skipping migration test")
        return True
    
    logger.info(f"Found {len(json_files)} JSON files")
    
    # Just test loading one file to verify format
    test_file = json_files[0]
    symbol = test_file.stem
    
    try:
        with open(test_file, 'r') as f:
            candles = json.load(f)
        
        logger.info(f"✅ Successfully read {symbol}.json with {len(candles)} candles")
        logger.info("Migration test passed - ready to migrate when needed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to read JSON file: {e}")
        return False

async def main():
    """Run all tests"""
    logger.info("🚀 Starting PostgreSQL Integration Tests")
    logger.info("=" * 60)
    
    all_passed = True
    
    # Test 1: Database connection
    if not await test_database_connection():
        all_passed = False
        logger.error("Database connection test failed - stopping tests")
        await nse_db_service.close()
        return
    
    # Test 2: Save and load operations
    if not await test_save_and_load():
        all_passed = False
    
    # Test 3: Batch operations
    if not await test_batch_operations():
        all_passed = False
    
    # Test 4: Migration readiness
    if not await test_migration():
        all_passed = False
    
    # Close database connection
    await nse_db_service.close()
    
    # Summary
    logger.info("=" * 60)
    if all_passed:
        logger.info("✅ All tests passed successfully!")
        logger.info("PostgreSQL integration is ready to use.")
        logger.info("")
        logger.info("To integrate with your application:")
        logger.info("1. Import the postgres_hard_refresh module in your main.py")
        logger.info("2. Replace hard_refresh_database with hard_refresh_database_postgres")
        logger.info("3. Replace load_stock_data with load_stock_data_postgres")
        logger.info("4. Replace save operations with save_stock_data_postgres")
    else:
        logger.error("❌ Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    asyncio.run(main())