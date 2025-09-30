"""
Database wrapper that uses ultra-fast unified database (no NSE database)
"""

import logging
from typing import Dict, List, Any, Optional

from .ultra_fast_database_service import ultra_fast_db

logger = logging.getLogger(__name__)

class DatabaseWrapper:
    """
    Wrapper for database operations using ultra-fast unified database.
    Eliminates NSE database completely - uses only nse_highspeed with composite keys.
    """
    
    def __init__(self):
        self.db_service = ultra_fast_db
        self._use_unified = True
        self._init_attempted = False
        
    async def initialize(self):
        """Initialize ultra-fast unified database connection."""
        if self._init_attempted:
            logger.debug(f"Already attempted initialization, returning: {self.db_service.initialized}")
            return self.db_service.initialized

        self._init_attempted = True

        try:
            logger.debug("Calling ultra_fast_db.initialize()...")
            result = await self.db_service.initialize()
            logger.debug(f"ultra_fast_db.initialize() returned: {result}")
            logger.debug(f"ultra_fast_db.initialized flag: {self.db_service.initialized}")

            if result and self.db_service.initialized:
                logger.info("✅ Using ultra-fast unified database (nse_highspeed) with composite keys")
                self._use_unified = True
                return True
            else:
                logger.warning(f"ultra_fast_db.initialize() returned {result} but initialized flag is {self.db_service.initialized}")
        except Exception as e:
            logger.error(f"Ultra-fast database initialization failed: {e}")
            self._init_attempted = False  # Reset so retry is possible
            raise Exception(f"Ultra-fast database is required but initialization failed: {e}")

        logger.warning("Returning False from db_wrapper.initialize()")
        return False
    
    async def save_candles(self, symbol: str, candles: List[Dict[str, Any]], 
                          timeframe: str = 'daily') -> bool:
        """
        Save candles to ultra-fast unified database with composite keys.
        
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
                success = await self.db_service.store_chunk_with_indicators(symbol, candles, timeframe)
                if success:
                    logger.debug(f"✅ Saved {len(candles)} {timeframe} candles for {symbol} with composite keys")
                    return True
                logger.error(f"❌ Ultra-fast database save failed for {symbol}")
                return False
            except Exception as e:
                logger.error(f"❌ Ultra-fast database save error for {symbol}: {e}")
                return False
        
        logger.error(f"❌ Cannot save {symbol}: Ultra-fast database not initialized")
        return False
    
    async def update_candles(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """
        Update candles (alias for save_candles for compatibility).
        
        Args:
            symbol: Stock symbol
            candles: List of candle data
            
        Returns:
            True if successful, False otherwise
        """
        return await self.save_candles(symbol, candles)

    async def update_latest_candle(self, symbol: str, candle: Dict[str, Any],
                                 timeframe: str = 'daily') -> bool:
        """
        Update or insert today's latest candle for a symbol.
        This is specifically for latest candle updates from cronjob.

        Args:
            symbol: Stock symbol
            candle: Single candle data dict
            timeframe: daily, weekly, or monthly

        Returns:
            True if successful, False otherwise
        """
        if not candle:
            return True

        if self._use_unified and self.db_service.initialized:
            try:
                success = await self.db_service.update_latest_candle(symbol, candle, timeframe)
                if success:
                    logger.debug(f"✅ Updated latest candle for {symbol}")
                    return True
                logger.error(f"❌ Latest candle update failed for {symbol}")
                return False
            except Exception as e:
                logger.error(f"❌ Latest candle update error for {symbol}: {e}")
                return False

        logger.error(f"❌ Cannot update latest candle for {symbol}: Ultra-fast database not initialized")
        return False

    async def load_candles(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load candles from PostgreSQL only.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of candles to load
            
        Returns:
            List of candle data or None
        """
        if self._use_unified and self.db_service.initialized:
            try:
                data = await self.db_service.get_last_n_candles(symbol, limit or 10000)
                if data:
                    return data
            except Exception as e:
                logger.error(f"Ultra-fast database load error for {symbol}: {e}")
                return None
        
        logger.error(f"Cannot load {symbol}: PostgreSQL not initialized")
        return None
    
    async def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest candle from ultra-fast database.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest candle data or None
        """
        if self._use_unified and self.db_service.initialized:
            try:
                candles = await self.db_service.get_last_n_candles(symbol, 1)
                if candles:
                    return candles[0]
            except Exception as e:
                logger.error(f"Ultra-fast database get latest error for {symbol}: {e}")
                return None
        
        logger.error(f"Cannot get latest candle for {symbol}: Ultra-fast database not initialized")
        return None
    
    async def close(self):
        """Close database connections."""
        if self.db_service.initialized:
            try:
                await self.db_service.close()
            except Exception as e:
                logger.warning(f"Error closing database: {e}")
    
    @property
    def initialized(self):
        """Check if PostgreSQL is initialized."""
        return self._use_unified and self.db_service.initialized
    
    @property
    def using_postgres(self):
        """Check if using PostgreSQL."""
        return self._use_unified and self.db_service.initialized

# Global instance
db_wrapper = DatabaseWrapper()

# Export convenience functions
async def save_candles_safe(symbol: str, candles: List[Dict[str, Any]]) -> bool:
    """Save candles to PostgreSQL only."""
    return await db_wrapper.save_candles(symbol, candles)

async def load_candles_safe(symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    """Load candles from PostgreSQL only."""
    return await db_wrapper.load_candles(symbol, limit)

async def get_latest_candle_safe(symbol: str) -> Optional[Dict[str, Any]]:
    """Get latest candle from PostgreSQL only."""
    return await db_wrapper.get_latest_candle(symbol)