"""
Migration script to move existing JSON data to TimescaleDB.
Run this script once to migrate all existing data from JSON files to the database.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any
from services.database_service import db_service
from utils.constants import STOCK_SYMBOLS
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def migrate_symbol(symbol: str, db_path: Path) -> Dict[str, Any]:
    """
    Migrate a single symbol from JSON to database.
    
    Args:
        symbol: Stock symbol
        db_path: Path to the db folder
        
    Returns:
        Migration result
    """
    try:
        # Check if JSON file exists
        json_file = db_path / f"{symbol}.json"
        if not json_file.exists():
            return {"symbol": symbol, "status": "skipped", "reason": "File not found"}
        
        # Load JSON data
        with open(json_file, 'r') as f:
            candles = json.load(f)
        
        if not candles:
            return {"symbol": symbol, "status": "skipped", "reason": "Empty file"}
        
        # Save to database
        success = await db_service.save_candles(symbol, candles)
        
        if success:
            return {
                "symbol": symbol, 
                "status": "success", 
                "candles": len(candles)
            }
        else:
            return {
                "symbol": symbol, 
                "status": "failed", 
                "reason": "Database save failed"
            }
            
    except Exception as e:
        logger.error(f"Error migrating {symbol}: {e}")
        return {
            "symbol": symbol, 
            "status": "error", 
            "reason": str(e)
        }

async def migrate_all_data(batch_size: int = 50):
    """
    Migrate all stock data from JSON files to TimescaleDB.
    
    Args:
        batch_size: Number of symbols to process concurrently
    """
    logger.info("Starting migration from JSON files to TimescaleDB...")
    
    # Initialize database
    try:
        await db_service.initialize()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return
    
    # Get db path
    db_path = Path(__file__).parent / "db"
    if not db_path.exists():
        logger.error(f"Database folder not found: {db_path}")
        return
    
    # Get all JSON files
    json_files = list(db_path.glob("*.json"))
    total_files = len(json_files)
    
    logger.info(f"Found {total_files} JSON files to migrate")
    
    # Migration statistics
    stats = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "error": 0,
        "total_candles": 0
    }
    
    # Process in batches
    start_time = time.time()
    
    for i in range(0, total_files, batch_size):
        batch_files = json_files[i:i + batch_size]
        batch_symbols = [f.stem for f in batch_files]
        
        # Process batch concurrently
        tasks = [migrate_symbol(symbol, db_path) for symbol in batch_symbols]
        results = await asyncio.gather(*tasks)
        
        # Update statistics
        for result in results:
            status = result.get("status")
            stats[status] = stats.get(status, 0) + 1
            
            if status == "success":
                stats["total_candles"] += result.get("candles", 0)
        
        # Progress update
        processed = min(i + batch_size, total_files)
        percentage = (processed / total_files) * 100
        logger.info(f"Progress: {processed}/{total_files} ({percentage:.1f}%) - "
                   f"Success: {stats['success']}, Failed: {stats['failed']}, "
                   f"Skipped: {stats['skipped']}, Error: {stats['error']}")
    
    # Final statistics
    elapsed_time = time.time() - start_time
    logger.info("\n" + "="*60)
    logger.info("Migration completed!")
    logger.info(f"Total time: {elapsed_time:.2f} seconds")
    logger.info(f"Files processed: {total_files}")
    logger.info(f"Successful migrations: {stats['success']}")
    logger.info(f"Failed migrations: {stats['failed']}")
    logger.info(f"Skipped files: {stats['skipped']}")
    logger.info(f"Errors: {stats['error']}")
    logger.info(f"Total candles migrated: {stats['total_candles']:,}")
    
    if stats['success'] > 0:
        logger.info(f"Average candles per symbol: {stats['total_candles'] // stats['success']:,}")
        logger.info(f"Migration rate: {stats['total_candles'] / elapsed_time:.0f} candles/second")
    
    # Close database connection
    await db_service.close()

async def verify_migration(sample_size: int = 10):
    """
    Verify that data was migrated correctly by comparing a sample.
    
    Args:
        sample_size: Number of symbols to verify
    """
    logger.info("\nVerifying migration...")
    
    # Initialize database
    await db_service.initialize()
    
    db_path = Path(__file__).parent / "db"
    json_files = list(db_path.glob("*.json"))[:sample_size]
    
    mismatches = []
    
    for json_file in json_files:
        symbol = json_file.stem
        
        # Load JSON data
        with open(json_file, 'r') as f:
            json_data = json.load(f)
        
        # Load database data
        db_data = await db_service.load_candles(symbol)
        
        if not db_data:
            mismatches.append(f"{symbol}: No data in database")
        elif len(json_data) != len(db_data):
            mismatches.append(f"{symbol}: Count mismatch - JSON: {len(json_data)}, DB: {len(db_data)}")
        else:
            # Compare first and last candles
            if json_data[0] != db_data[0]:
                mismatches.append(f"{symbol}: First candle mismatch")
            if json_data[-1] != db_data[-1]:
                mismatches.append(f"{symbol}: Last candle mismatch")
    
    if mismatches:
        logger.warning(f"Found {len(mismatches)} mismatches:")
        for mismatch in mismatches:
            logger.warning(f"  - {mismatch}")
    else:
        logger.info(f"✓ Verification successful! All {sample_size} samples match perfectly.")
    
    await db_service.close()

async def main():
    """Main migration function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate stock data from JSON to TimescaleDB")
    parser.add_argument("--batch-size", type=int, default=50, 
                       help="Number of symbols to process concurrently (default: 50)")
    parser.add_argument("--verify", action="store_true", 
                       help="Verify migration after completion")
    parser.add_argument("--verify-only", action="store_true", 
                       help="Only run verification without migration")
    parser.add_argument("--sample-size", type=int, default=10,
                       help="Number of symbols to verify (default: 10)")
    
    args = parser.parse_args()
    
    if args.verify_only:
        await verify_migration(args.sample_size)
    else:
        await migrate_all_data(args.batch_size)
        
        if args.verify:
            await verify_migration(args.sample_size)

if __name__ == "__main__":
    asyncio.run(main())