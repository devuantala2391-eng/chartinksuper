"""
Database wrapper that provides PostgreSQL access only (file storage disabled)
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import asyncio

from .nse_database_service import nse_db_service

logger = logging.getLogger(__name__)

class DatabaseWrapper:
    """
    Wrapper for database operations with PostgreSQL only.
    File storage fallback is disabled - PostgreSQL is required.
    """
    
    def __init__(self):
        self.db_service = nse_db_service
        # File storage path commented out for future use
        # self.db_path = Path(__file__).parent.parent / "db"
        # self.db_path.mkdir(exist_ok=True)
        self._use_postgres = True
        self._init_attempted = False
        
    async def initialize(self):
        """Initialize database connection (PostgreSQL only)."""
        if self._init_attempted:
            return self.db_service.initialized
            
        self._init_attempted = True
        
        try:
            await self.db_service.initialize()
            if self.db_service.initialized:
                logger.info("Using PostgreSQL database for storage")
                self._use_postgres = True
                return True
        except Exception as e:
            logger.error(f"PostgreSQL initialization failed: {e}")
            raise Exception(f"PostgreSQL is required but initialization failed: {e}")
        
        # File storage fallback disabled
        # logger.info("Using file-based storage (fallback mode)")
        # self._use_postgres = False
        return False
    
    async def save_candles(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """
        Save candles to PostgreSQL only (no file storage fallback).
        
        Args:
            symbol: Stock symbol
            candles: List of candle data
            
        Returns:
            True if successful, False otherwise
        """
        if not candles:
            return True
        
        # PostgreSQL only - no fallback
        if self._use_postgres and self.db_service.initialized:
            try:
                success = await self.db_service.save_candles(symbol, candles)
                if success:
                    return True
                logger.error(f"PostgreSQL save failed for {symbol}")
                return False
            except Exception as e:
                logger.error(f"PostgreSQL save error for {symbol}: {e}")
                return False
        
        # File storage fallback disabled - kept for future use
        # try:
        #     file_path = self.db_path / f"{symbol}.json"
        #     with open(file_path, 'w') as f:
        #         json.dump(candles, f)
        #     logger.debug(f"Saved {symbol} to file (fallback)")
        #     return True
        # except Exception as e:
        #     logger.error(f"File save failed for {symbol}: {e}")
        #     return False
        
        logger.error(f"Cannot save {symbol}: PostgreSQL not initialized")
        return False
    
    async def load_candles(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load candles from PostgreSQL only (no file storage fallback).
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of candles to load
            
        Returns:
            List of candle data or None
        """
        # PostgreSQL only - no fallback
        if self._use_postgres and self.db_service.initialized:
            try:
                data = await self.db_service.load_candles(symbol, limit)
                if data:
                    return data
            except Exception as e:
                logger.error(f"PostgreSQL load error for {symbol}: {e}")
                return None
        
        # File storage fallback disabled - kept for future use
        # try:
        #     file_path = self.db_path / f"{symbol}.json"
        #     if file_path.exists():
        #         with open(file_path, 'r') as f:
        #             data = json.load(f)
        #             if limit:
        #                 return data[-limit:]
        #             return data
        # except Exception as e:
        #     logger.error(f"File load failed for {symbol}: {e}")
        
        logger.error(f"Cannot load {symbol}: PostgreSQL not initialized")
        return None
    
    async def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest candle from PostgreSQL only (no file storage fallback).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest candle data or None
        """
        # PostgreSQL only - no fallback
        if self._use_postgres and self.db_service.initialized:
            try:
                candle = await self.db_service.get_latest_candle(symbol)
                if candle:
                    return candle
            except Exception as e:
                logger.error(f"PostgreSQL get latest error for {symbol}: {e}")
                return None
        
        # File storage fallback disabled
        # data = await self.load_candles(symbol, limit=1)
        # if data:
        #     return data[-1]
        
        logger.error(f"Cannot get latest candle for {symbol}: PostgreSQL not initialized")
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
        return self._use_postgres and self.db_service.initialized
    
    @property
    def using_postgres(self):
        """Check if using PostgreSQL."""
        return self._use_postgres and self.db_service.initialized

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