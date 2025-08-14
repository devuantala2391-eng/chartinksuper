"""
PostgreSQL-based Hard Refresh Implementation
This module replaces the file-based hard refresh with PostgreSQL storage
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from services.nse_database_service import nse_db_service
from services.postgres_integration import postgres_integration
from services.chartink_service import get_default_candle_count

logger = logging.getLogger(__name__)

async def hard_refresh_database_postgres(stock_symbols: List[str], 
                                        update_progress_func=None,
                                        progress_queue=None):
    """
    Hard refresh implementation using PostgreSQL database.
    Replaces the file-based storage with high-performance database storage.
    
    Args:
        stock_symbols: List of stock symbols to refresh
        update_progress_func: Function to update progress
        progress_queue: Queue for progress updates
    
    Returns:
        Dictionary with refresh results
    """
    try:
        logger.info("Starting HARD REFRESH with PostgreSQL - cleaning all data and refetching")
        
        # Get candle count from environment
        candle_count = get_default_candle_count()
        logger.info(f"Using candle count from env: {candle_count}")
        
        # Initialize database
        await nse_db_service.initialize()
        
        # Clear all existing data
        logger.info("Clearing existing data from PostgreSQL database...")
        await nse_db_service.delete_all_data()
        
        # Reset progress
        if update_progress_func:
            update_progress_func({
                "isRunning": True,
                "phase": "initializing",
                "message": f"Hard refresh started - fetching {candle_count} candles per stock (PostgreSQL)",
                "processed": 0,
                "total": len(stock_symbols),
                "status": "running"
            }, clear_queue=True)
        
        total_symbols = len(stock_symbols)
        
        # Progress callback
        processed = 0
        successful = 0
        failed = 0
        
        async def progress_callback(symbol: str, success: bool):
            nonlocal processed, successful, failed
            processed += 1
            if success:
                successful += 1
            else:
                failed += 1
            
            if update_progress_func:
                update_progress_func({
                    "isRunning": True,
                    "phase": "fetching_data",
                    "message": f"Processing {symbol} ({processed}/{total_symbols})",
                    "processed": processed,
                    "total": total_symbols,
                    "successful": successful,
                    "failed": failed,
                    "symbol": symbol,
                    "status": "running"
                })
            
            if progress_queue:
                try:
                    progress_queue.put_nowait({
                        "phase": "fetching_data",
                        "processed": processed,
                        "total": total_symbols,
                        "successful": successful,
                        "failed": failed,
                        "symbol": symbol
                    })
                except:
                    pass
        
        # Start the hard refresh with PostgreSQL
        start_time = time.time()
        results = await postgres_integration.hard_refresh_with_postgres(
            stock_symbols, 
            candle_count,
            progress_callback
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Get database statistics
        db_stats = await nse_db_service.get_database_stats()
        
        # Update final progress
        if update_progress_func:
            update_progress_func({
                "isRunning": False,
                "phase": "completed",
                "message": f"Hard refresh completed in {processing_time:.2f} seconds",
                "processed": processed,
                "total": total_symbols,
                "successful": successful,
                "failed": failed,
                "processingTime": processing_time,
                "databaseStats": db_stats,
                "status": "completed"
            })
        
        logger.info(f"Hard refresh completed - Successful: {successful}, Failed: {failed}, Time: {processing_time:.2f}s")
        logger.info(f"Database stats: {db_stats}")
        
        return {
            "success": True,
            "message": f"Hard refresh completed - stored in PostgreSQL database",
            "processed": processed,
            "successful": successful,
            "failed": failed,
            "processingTime": processing_time,
            "databaseStats": db_stats,
            "results": results
        }
        
    except Exception as error:
        logger.error(f"Hard refresh failed: {error}")
        
        if update_progress_func:
            update_progress_func({
                "isRunning": False,
                "phase": "error",
                "message": f"Hard refresh failed: {str(error)}",
                "status": "error",
                "error": str(error)
            })
        
        return {
            "success": False,
            "message": f"Hard refresh failed: {str(error)}",
            "error": str(error)
        }

async def load_stock_data_postgres(symbol: str) -> Optional[List[Dict]]:
    """
    Load stock data from PostgreSQL database.
    Drop-in replacement for file-based loading.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of candle data or None
    """
    try:
        return await nse_db_service.load_stock_data(symbol)
    except Exception as e:
        logger.error(f"Error loading {symbol} from PostgreSQL: {e}")
        return None

def load_stock_data_sync_postgres(symbol: str) -> Optional[List[Dict]]:
    """
    Synchronous version of load_stock_data for compatibility.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of candle data or None
    """
    try:
        # Create a new event loop for sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(load_stock_data_postgres(symbol))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error loading {symbol} from PostgreSQL (sync): {e}")
        return None

async def save_stock_data_postgres(symbol: str, candles: List[Dict]) -> bool:
    """
    Save stock data to PostgreSQL database.
    Drop-in replacement for file-based saving.
    
    Args:
        symbol: Stock symbol
        candles: List of candle data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        return await nse_db_service.save_stock_data(symbol, candles)
    except Exception as e:
        logger.error(f"Error saving {symbol} to PostgreSQL: {e}")
        return False

async def update_stock_data_postgres(symbol: str, new_candles: List[Dict]) -> bool:
    """
    Update stock data with new candles in PostgreSQL.
    
    Args:
        symbol: Stock symbol
        new_candles: List of new candle data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        return await nse_db_service.update_or_insert_candles(symbol, new_candles)
    except Exception as e:
        logger.error(f"Error updating {symbol} in PostgreSQL: {e}")
        return False

async def get_all_symbols_postgres() -> List[str]:
    """
    Get all stock symbols from PostgreSQL database.
    
    Returns:
        List of symbol strings
    """
    try:
        return await nse_db_service.get_all_symbols()
    except Exception as e:
        logger.error(f"Error getting symbols from PostgreSQL: {e}")
        return []

async def get_latest_candle_postgres(symbol: str) -> Optional[Dict]:
    """
    Get the latest candle for a symbol from PostgreSQL.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Latest candle data or None
    """
    try:
        return await nse_db_service.get_latest_candle(symbol)
    except Exception as e:
        logger.error(f"Error getting latest candle for {symbol}: {e}")
        return None

async def migrate_json_files_to_postgres():
    """
    Migrate existing JSON files to PostgreSQL database.
    One-time migration function.
    """
    try:
        db_path = Path(__file__).parent / "db"
        
        if not db_path.exists():
            logger.info("No db directory found, nothing to migrate")
            return {
                "success": True,
                "message": "No data to migrate"
            }
        
        logger.info("Starting migration of JSON files to PostgreSQL...")
        
        # Initialize database
        await nse_db_service.initialize()
        
        # Get all JSON files
        json_files = list(db_path.glob("*.json"))
        total_files = len(json_files)
        
        if total_files == 0:
            logger.info("No JSON files found to migrate")
            return {
                "success": True,
                "message": "No JSON files to migrate"
            }
        
        logger.info(f"Found {total_files} JSON files to migrate")
        
        # Migrate using the integration module
        results = await postgres_integration.migrate_json_to_postgres(db_path)
        
        successful = sum(1 for success in results.values() if success)
        failed = total_files - successful
        
        # Get database stats after migration
        db_stats = await nse_db_service.get_database_stats()
        
        logger.info(f"Migration completed - Successful: {successful}, Failed: {failed}")
        logger.info(f"Database stats: {db_stats}")
        
        return {
            "success": True,
            "message": f"Migration completed - {successful} files migrated successfully",
            "total": total_files,
            "successful": successful,
            "failed": failed,
            "databaseStats": db_stats,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {
            "success": False,
            "message": f"Migration failed: {str(e)}",
            "error": str(e)
        }

# Export functions for easy import
__all__ = [
    'hard_refresh_database_postgres',
    'load_stock_data_postgres',
    'load_stock_data_sync_postgres',
    'save_stock_data_postgres',
    'update_stock_data_postgres',
    'get_all_symbols_postgres',
    'get_latest_candle_postgres',
    'migrate_json_files_to_postgres'
]