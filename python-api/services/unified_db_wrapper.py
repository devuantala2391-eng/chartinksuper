"""
Unified Database Wrapper - Replaces the old dual-database system
- Eliminates NSE database completely
- Uses only the ultra-fast unified database
- Provides compatibility interface for existing code
- Supports all timeframes (daily, weekly, monthly)
"""

import logging
from typing import Dict, List, Any, Optional
from .ultra_fast_database_service import ultra_fast_db

logger = logging.getLogger(__name__)

class UnifiedDatabaseWrapper:
    """
    Unified database wrapper that replaces the old NSE + High-Speed dual database system.
    Everything now goes through the ultra-fast database with composite keys.
    """
    
    def __init__(self):
        self.db_service = ultra_fast_db
        self._use_unified = True
        self._init_attempted = False
        
        logger.info("🚀 Unified Database Wrapper initialized - NSE database eliminated!")

    async def initialize(self):
        """Initialize unified database connection."""
        if self._init_attempted:
            return self.db_service.initialized
            
        self._init_attempted = True
        
        try:
            await self.db_service.initialize()
            if self.db_service.initialized:
                logger.info("✅ Using unified ultra-fast database for all operations")
                self._use_unified = True
                return True
        except Exception as e:
            logger.error(f"Unified database initialization failed: {e}")
            raise Exception(f"Unified database is required but initialization failed: {e}")
        
        return False

    async def save_candles(self, symbol: str, candles: List[Dict[str, Any]], 
                          timeframe: str = 'daily') -> bool:
        """
        Save candles with indicators to unified database.
        
        Args:
            symbol: Stock symbol
            candles: List of candle data with indicators
            timeframe: daily, weekly, or monthly
            
        Returns:
            True if successful, False otherwise
        """
        if not candles:
            return True
        
        if self._use_unified and self.db_service.initialized:
            try:
                # Use the streaming chunk storage for optimal performance
                success = await self.db_service.store_chunk_with_indicators(
                    symbol, candles, timeframe
                )
                if success:
                    logger.debug(f"✅ Saved {len(candles)} {timeframe} candles for {symbol}")
                    return True
                logger.error(f"❌ Unified database save failed for {symbol}")
                return False
            except Exception as e:
                logger.error(f"❌ Unified database save error for {symbol}: {e}")
                return False
        
        logger.error(f"❌ Cannot save {symbol}: Unified database not initialized")
        return False

    async def update_candles(self, symbol: str, candles: List[Dict[str, Any]], 
                            timeframe: str = 'daily') -> bool:
        """
        Update candles (alias for save_candles for compatibility).
        In the unified system, save and update are the same operation (UPSERT).
        """
        return await self.save_candles(symbol, candles, timeframe)

    async def load_candles(self, symbol: str, limit: Optional[int] = None, 
                          timeframe: str = 'daily') -> Optional[List[Dict[str, Any]]]:
        """
        Load candles from unified database.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of candles to load (most recent)
            timeframe: daily, weekly, or monthly
            
        Returns:
            List of candle data with indicators or None
        """
        if self._use_unified and self.db_service.initialized:
            try:
                if limit:
                    data = await self.db_service.get_last_n_candles(symbol, limit, timeframe)
                else:
                    # Get all candles for symbol
                    data = await self.db_service.get_last_n_candles(symbol, 10000, timeframe)
                
                if data:
                    logger.debug(f"📥 Loaded {len(data)} {timeframe} candles for {symbol}")
                    return data
                else:
                    logger.debug(f"📭 No {timeframe} candles found for {symbol}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Unified database load error for {symbol}: {e}")
                return None
        
        logger.error(f"❌ Cannot load {symbol}: Unified database not initialized")
        return None

    async def get_latest_candle(self, symbol: str, timeframe: str = 'daily') -> Optional[Dict[str, Any]]:
        """Get the latest candle for a symbol with all indicators"""
        try:
            candles = await self.get_last_n_candles(symbol, 1, timeframe)
            return candles[0] if candles else None
        except Exception as e:
            logger.error(f"❌ Error getting latest candle for {symbol}: {e}")
            return None

    async def get_last_n_candles(self, symbol: str, n: int, 
                                timeframe: str = 'daily') -> List[Dict[str, Any]]:
        """
        Get last N candles for a symbol (optimized with composite keys).
        This uses O(1) lookups with the SYMBOL_KEY system.
        """
        if self._use_unified and self.db_service.initialized:
            try:
                data = await self.db_service.get_last_n_candles(symbol, n, timeframe)
                return data if data else []
            except Exception as e:
                logger.error(f"❌ Error getting last {n} candles for {symbol}: {e}")
                return []
        
        return []

    async def get_candle_n_days_ago(self, symbol: str, days_ago: int, 
                                   timeframe: str = 'daily') -> Optional[Dict[str, Any]]:
        """
        Get candle from N days ago using O(1) composite key lookup.
        Example: get_candle_n_days_ago("RELIANCE", 5) gets RELIANCE candle from 5 days ago.
        """
        if self._use_unified and self.db_service.initialized:
            try:
                return await self.db_service.get_candle_n_days_ago(symbol, days_ago, timeframe)
            except Exception as e:
                logger.error(f"❌ Error getting {days_ago} days ago candle for {symbol}: {e}")
                return None
        
        return None

    async def query_by_indicators(self, indicator_conditions: List[Dict], 
                                 symbols: List[str] = None,
                                 timeframe: str = 'daily') -> List[Dict]:
        """
        Query stocks by indicator conditions using JSONB indexes.
        
        Example:
        conditions = [
            {'name': 'rsi_14', 'operator': '>', 'value': 70},
            {'name': 'supertrend_10_2', 'operator': '<', 'value': 100}
        ]
        """
        if self._use_unified and self.db_service.initialized:
            try:
                return await self.db_service.query_by_indicators(
                    indicator_conditions, symbols, timeframe
                )
            except Exception as e:
                logger.error(f"❌ Error querying by indicators: {e}")
                return []
        
        return []

    async def get_all_symbols(self, timeframe: str = 'daily') -> List[str]:
        """Get list of all symbols in the unified database"""
        if self._use_unified and self.db_service.initialized:
            try:
                async with self.db_service.get_connection() as conn:
                    table_name = f"{timeframe}_candles"
                    rows = await conn.fetch(f"""
                        SELECT DISTINCT symbol 
                        FROM {table_name} 
                        ORDER BY symbol
                    """)
                    
                    return [row['symbol'] for row in rows]
                    
            except Exception as e:
                logger.error(f"❌ Error getting all symbols: {e}")
                return []
        
        return []

    async def get_candles_between(self, symbol: str, start_timestamp: int, 
                                 end_timestamp: int, timeframe: str = 'daily') -> List[Dict[str, Any]]:
        """Get candles between two timestamps"""
        if self._use_unified and self.db_service.initialized:
            try:
                async with self.db_service.get_connection() as conn:
                    table_name = f"{timeframe}_candles"
                    rows = await conn.fetch(f"""
                        SELECT * FROM {table_name}
                        WHERE symbol = $1 AND timestamp >= $2 AND timestamp <= $3
                        ORDER BY key_number ASC
                    """, symbol, start_timestamp, end_timestamp)
                    
                    results = []
                    for row in rows:
                        result = dict(row)
                        # Parse indicators from JSONB
                        if result.get('indicators'):
                            import json
                            indicators = json.loads(result['indicators']) if isinstance(result['indicators'], str) else result['indicators']
                            result.update(indicators)
                        results.append(result)
                    
                    return results
                    
            except Exception as e:
                logger.error(f"❌ Error getting candles between timestamps for {symbol}: {e}")
                return []
        
        return []

    async def save_stock_data_batch(self, stock_data_list: List[Tuple[str, List[Dict]]], 
                                   timeframe: str = 'daily') -> Dict[str, bool]:
        """
        Save multiple stocks' data efficiently using the streaming processor.
        This leverages the parallel processing capabilities.
        """
        results = {}
        
        try:
            # Use the streaming processor for maximum efficiency
            from .streaming_pipeline_processor import streaming_processor
            await streaming_processor.initialize()
            
            for symbol, candles in stock_data_list:
                if candles:
                    success = await self.save_candles(symbol, candles, timeframe)
                    results[symbol] = success
                else:
                    results[symbol] = True
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Failed to batch save stock data: {e}")
            return {symbol: False for symbol, _ in stock_data_list}

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        if self._use_unified and self.db_service.initialized:
            try:
                return await self.db_service.get_database_stats()
            except Exception as e:
                logger.error(f"❌ Failed to get database stats: {e}")
                return {}
        
        return {}

    async def health_check(self) -> bool:
        """Comprehensive health check"""
        if self._use_unified and self.db_service.initialized:
            return await self.db_service.health_check()
        return False

    async def delete_all_data(self, timeframe: str = 'daily') -> bool:
        """
        Delete all data from unified database (use with caution).
        """
        if self._use_unified and self.db_service.initialized:
            try:
                async with self.db_service.get_connection() as conn:
                    table_name = f"{timeframe}_candles"
                    await conn.execute(f"TRUNCATE TABLE {table_name} CASCADE")
                    await conn.execute("TRUNCATE TABLE symbol_metadata CASCADE")
                    
                logger.info(f"🗑️ All {timeframe} data deleted from unified database")
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to delete all data: {e}")
                return False
        
        return False

    # Compatibility methods for old code
    async def save_stock_data(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """Compatibility method - routes to save_candles"""
        return await self.save_candles(symbol, candles)

    async def load_stock_data(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """Compatibility method - routes to load_candles"""
        return await self.load_candles(symbol, limit)

    async def update_or_insert_candles(self, symbol: str, new_candles: List[Dict[str, Any]]) -> bool:
        """Compatibility method - routes to save_candles (which does UPSERT)"""
        return await self.save_candles(symbol, new_candles)

    async def close(self):
        """Close the unified database connection"""
        if self.db_service:
            await self.db_service.close()
            logger.info("🔒 Unified database connection closed")

# Global instance - replaces the old db_wrapper
unified_db_wrapper = UnifiedDatabaseWrapper()