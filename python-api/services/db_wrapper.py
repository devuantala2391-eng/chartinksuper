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
            return self.db_service.initialized
            
        self._init_attempted = True
        
        try:
            await self.db_service.initialize()
            if self.db_service.initialized:
                logger.info("✅ Using ultra-fast unified database (nse_highspeed) with composite keys")
                self._use_unified = True
                return True
        except Exception as e:
            logger.error(f"Ultra-fast database initialization failed: {e}")
            raise Exception(f"Ultra-fast database is required but initialization failed: {e}")
        
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