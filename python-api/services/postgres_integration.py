"""
PostgreSQL Integration Module
This module provides wrapper functions to integrate the NSE database service
with the existing application, replacing JSON file storage with PostgreSQL.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import time

from .nse_database_service import nse_db_service
from .chartink_service import ChartinkService

logger = logging.getLogger(__name__)

class PostgresIntegration:
    """
    Integration layer for PostgreSQL database operations.
    Provides drop-in replacements for file-based operations.
    """
    
    def __init__(self):
        self.db_service = nse_db_service
        self.chartink_service = ChartinkService()
        self.batch_size = 50  # Number of stocks to process in parallel
        
    async def initialize(self):
        """Initialize the database connection and create tables"""
        await self.db_service.initialize()
        logger.info("PostgreSQL integration initialized")
    
    async def hard_refresh_with_postgres(self, stock_symbols: List[str], 
                                        candle_count: int,
                                        progress_callback=None) -> Dict[str, bool]:
        """
        Perform a hard refresh storing all data in PostgreSQL.
        
        Args:
            stock_symbols: List of stock symbols to refresh
            candle_count: Number of candles to fetch per stock
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary mapping symbols to success status
        """
        results = {}
        total_stocks = len(stock_symbols)
        processed = 0
        successful = 0
        failed = 0
        
        try:
            # Initialize database
            await self.initialize()
            
            # Clear all existing data
            logger.info("Clearing existing data from database...")
            await self.db_service.delete_all_data()
            
            # Initialize Chartink service
            await self.chartink_service.initialize_client_pool()
            
            # Process stocks in batches for optimal performance
            for i in range(0, total_stocks, self.batch_size):
                batch_symbols = stock_symbols[i:i + self.batch_size]
                batch_start = time.time()
                
                # Fetch data for batch in parallel
                fetch_tasks = []
                for symbol in batch_symbols:
                    task = self._fetch_and_store_stock(symbol, candle_count)
                    fetch_tasks.append(task)
                
                # Execute batch
                batch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                
                # Process results
                for symbol, result in zip(batch_symbols, batch_results):
                    processed += 1
                    
                    if isinstance(result, Exception):
                        logger.error(f"Error processing {symbol}: {result}")
                        results[symbol] = False
                        failed += 1
                    elif result:
                        results[symbol] = True
                        successful += 1
                    else:
                        results[symbol] = False
                        failed += 1
                    
                    # Update progress
                    if progress_callback:
                        await progress_callback(symbol, results[symbol])
                
                batch_time = time.time() - batch_start
                logger.info(f"Batch {i//self.batch_size + 1} completed in {batch_time:.2f}s - "
                          f"Processed: {processed}/{total_stocks}, "
                          f"Success: {successful}, Failed: {failed}")
            
            # Get final stats
            stats = await self.db_service.get_database_stats()
            logger.info(f"Hard refresh completed. Database stats: {stats}")
            
            return results
            
        except Exception as e:
            logger.error(f"Hard refresh failed: {e}")
            raise
        finally:
            await self.chartink_service.close_all_clients()
    
    async def _fetch_and_store_stock(self, symbol: str, candle_count: int) -> bool:
        """
        Fetch stock data from Chartink and store in PostgreSQL.
        
        Args:
            symbol: Stock symbol
            candle_count: Number of candles to fetch
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch data from Chartink
            response = await self.chartink_service.fetch_stock_data(symbol, candle_count)
            
            if not response or 'data' not in response:
                logger.warning(f"No data received for {symbol}")
                return False
            
            candles = response['data']
            
            if not candles:
                logger.warning(f"Empty candle data for {symbol}")
                return False
            
            # Store in PostgreSQL
            success = await self.db_service.save_stock_data(symbol, candles)
            
            if success:
                logger.debug(f"Successfully stored {len(candles)} candles for {symbol}")
            else:
                logger.error(f"Failed to store data for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error fetching/storing {symbol}: {e}")
            return False
    
    async def update_stock_data(self, symbol: str, new_candles: List[Dict]) -> bool:
        """
        Update stock data with new candles (used for incremental updates).
        
        Args:
            symbol: Stock symbol
            new_candles: List of new candle data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.db_service.update_or_insert_candles(symbol, new_candles)
        except Exception as e:
            logger.error(f"Error updating stock data for {symbol}: {e}")
            return False
    
    async def load_stock_data_from_postgres(self, symbol: str) -> Optional[List[Dict]]:
        """
        Load stock data from PostgreSQL (drop-in replacement for JSON loading).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            List of candle data or None
        """
        try:
            return await self.db_service.load_stock_data(symbol)
        except Exception as e:
            logger.error(f"Error loading stock data for {symbol}: {e}")
            return None
    
    async def load_multiple_stocks_from_postgres(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """
        Load data for multiple stocks from PostgreSQL.
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary mapping symbols to candle data
        """
        try:
            return await self.db_service.load_multiple_stocks(symbols)
        except Exception as e:
            logger.error(f"Error loading multiple stocks: {e}")
            return {symbol: None for symbol in symbols}
    
    async def save_precalculated_data(self, symbol: str, 
                                     precalc_data: List[Dict]) -> bool:
        """
        Save precalculated indicator data to PostgreSQL.
        
        Args:
            symbol: Stock symbol
            precalc_data: List of precalculated data with timestamps
            
        Returns:
            True if successful, False otherwise
        """
        try:
            for data_point in precalc_data:
                timestamp = data_point.get('timestamp')
                if timestamp:
                    # Remove timestamp from indicators dict
                    indicators = {k: v for k, v in data_point.items() if k != 'timestamp'}
                    success = await self.db_service.save_precalculated_indicators(
                        symbol, timestamp, indicators
                    )
                    if not success:
                        return False
            return True
        except Exception as e:
            logger.error(f"Error saving precalculated data for {symbol}: {e}")
            return False
    
    async def load_precalculated_data(self, symbol: str) -> Optional[List[Dict]]:
        """
        Load precalculated indicator data from PostgreSQL.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            List of precalculated data or None
        """
        try:
            return await self.db_service.load_precalculated_indicators(symbol)
        except Exception as e:
            logger.error(f"Error loading precalculated data for {symbol}: {e}")
            return None
    
    async def get_latest_candle(self, symbol: str) -> Optional[Dict]:
        """
        Get the latest candle for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest candle data or None
        """
        try:
            return await self.db_service.get_latest_candle(symbol)
        except Exception as e:
            logger.error(f"Error getting latest candle for {symbol}: {e}")
            return None
    
    async def get_all_symbols(self) -> List[str]:
        """
        Get list of all symbols in the database.
        
        Returns:
            List of symbol strings
        """
        try:
            return await self.db_service.get_all_symbols()
        except Exception as e:
            logger.error(f"Error getting all symbols: {e}")
            return []
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            return await self.db_service.get_database_stats()
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}
    
    async def migrate_json_to_postgres(self, db_path: Path) -> Dict[str, bool]:
        """
        Migrate existing JSON files to PostgreSQL.
        
        Args:
            db_path: Path to directory containing JSON files
            
        Returns:
            Dictionary mapping symbols to migration success status
        """
        results = {}
        
        try:
            # Initialize database
            await self.initialize()
            
            # Get all JSON files
            json_files = list(db_path.glob("*.json"))
            total_files = len(json_files)
            
            logger.info(f"Found {total_files} JSON files to migrate")
            
            # Process files in batches
            for i in range(0, total_files, self.batch_size):
                batch_files = json_files[i:i + self.batch_size]
                batch_data = []
                
                # Load JSON data
                for json_file in batch_files:
                    symbol = json_file.stem
                    try:
                        with open(json_file, 'r') as f:
                            candles = json.load(f)
                            batch_data.append((symbol, candles))
                    except Exception as e:
                        logger.error(f"Error reading {json_file}: {e}")
                        results[symbol] = False
                
                # Store batch in database
                if batch_data:
                    batch_results = await self.db_service.save_stock_data_batch(batch_data)
                    results.update(batch_results)
                
                logger.info(f"Migrated batch {i//self.batch_size + 1}/{(total_files + self.batch_size - 1)//self.batch_size}")
            
            # Get final stats
            stats = await self.db_service.get_database_stats()
            logger.info(f"Migration completed. Database stats: {stats}")
            
            return results
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

# Global instance
postgres_integration = PostgresIntegration()

# Export convenience functions for drop-in replacement
async def hard_refresh_postgres(stock_symbols: List[str], candle_count: int, progress_callback=None):
    """Convenience function for hard refresh with PostgreSQL"""
    return await postgres_integration.hard_refresh_with_postgres(stock_symbols, candle_count, progress_callback)

async def load_stock_data_postgres(symbol: str):
    """Convenience function to load stock data from PostgreSQL"""
    return await postgres_integration.load_stock_data_from_postgres(symbol)

async def save_stock_data_postgres(symbol: str, candles: List[Dict]):
    """Convenience function to save stock data to PostgreSQL"""
    return await nse_db_service.save_stock_data(symbol, candles)

async def migrate_to_postgres(db_path: Path):
    """Convenience function to migrate JSON files to PostgreSQL"""
    return await postgres_integration.migrate_json_to_postgres(db_path)