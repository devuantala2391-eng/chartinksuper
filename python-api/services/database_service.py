"""
TimescaleDB service for storing and retrieving candle data.
Replaces file-based storage with high-performance time-series database.
"""

import os
import json
import logging
import asyncio
import asyncpg
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Service for managing TimescaleDB connections and operations.
    Provides high-performance storage for time-series candle data.
    """
    
    def __init__(self):
        # Database connection parameters from environment
        self.db_config = {
            'host': os.getenv('TIMESCALE_HOST', 'localhost'),
            'port': int(os.getenv('TIMESCALE_PORT', '5432')),
            'database': os.getenv('TIMESCALE_DB', 'chartink'),
            'user': os.getenv('TIMESCALE_USER', 'postgres'),
            'password': os.getenv('TIMESCALE_PASSWORD', 'postgres'),
        }
        
        self.pool = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize database connection pool and create tables."""
        if self.initialized:
            return
            
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                **self.db_config,
                min_size=10,
                max_size=50,
                command_timeout=60
            )
            
            # Create tables if they don't exist
            await self._create_tables()
            
            self.initialized = True
            logger.info("Database service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _create_tables(self):
        """Create TimescaleDB tables for candle data."""
        async with self.pool.acquire() as conn:
            # Create main candle data table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS candle_data (
                    symbol VARCHAR(50) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    date VARCHAR(10),
                    time VARCHAR(8),
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume BIGINT,
                    PRIMARY KEY (symbol, timestamp)
                );
            """)
            
            # Create hypertable for time-series optimization
            await conn.execute("""
                SELECT create_hypertable('candle_data', 'timestamp',
                    chunk_time_interval => 86400000,
                    if_not_exists => TRUE
                );
            """)
            
            # Create indexes for fast queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candle_symbol 
                ON candle_data (symbol);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candle_timestamp 
                ON candle_data (timestamp DESC);
            """)
            
            # Create table for latest candle cache
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS latest_candles (
                    symbol VARCHAR(50) PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    date VARCHAR(10),
                    time VARCHAR(8),
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume BIGINT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create table for indicator data
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS indicator_data (
                    symbol VARCHAR(50) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    indicator_name VARCHAR(100) NOT NULL,
                    indicator_data JSONB,
                    PRIMARY KEY (symbol, timestamp, indicator_name)
                );
            """)
            
            # Create hypertable for indicators
            await conn.execute("""
                SELECT create_hypertable('indicator_data', 'timestamp',
                    chunk_time_interval => 86400000,
                    if_not_exists => TRUE
                );
            """)
            
            logger.info("Database tables created successfully")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool."""
        if not self.initialized:
            await self.initialize()
        
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)
    
    # ============= Write Operations =============
    
    async def save_candles(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """
        Save candle data to TimescaleDB.
        
        Args:
            symbol: Stock symbol
            candles: List of candle dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not candles:
            return True
            
        try:
            async with self.get_connection() as conn:
                # Prepare data for bulk insert
                values = []
                for candle in candles:
                    values.append((
                        symbol,
                        candle.get('timestamp', 0),
                        candle.get('date', ''),
                        candle.get('time', ''),
                        float(candle.get('open', 0)),
                        float(candle.get('high', 0)),
                        float(candle.get('low', 0)),
                        float(candle.get('close', 0)),
                        int(candle.get('volume', 0))
                    ))
                
                # Use COPY for fast bulk insert
                await conn.copy_records_to_table(
                    'candle_data',
                    records=values,
                    columns=['symbol', 'timestamp', 'date', 'time', 
                            'open', 'high', 'low', 'close', 'volume']
                )
                
                # Update latest candle cache
                if candles:
                    latest = max(candles, key=lambda x: x.get('timestamp', 0))
                    await self._update_latest_candle(conn, symbol, latest)
                
                logger.debug(f"Saved {len(candles)} candles for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save candles for {symbol}: {e}")
            return False
    
    async def _update_latest_candle(self, conn, symbol: str, candle: Dict[str, Any]):
        """Update the latest candle cache for a symbol."""
        await conn.execute("""
            INSERT INTO latest_candles 
            (symbol, timestamp, date, time, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol) 
            DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                date = EXCLUDED.date,
                time = EXCLUDED.time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                updated_at = CURRENT_TIMESTAMP
        """, symbol, candle.get('timestamp', 0), candle.get('date', ''),
            candle.get('time', ''), float(candle.get('open', 0)),
            float(candle.get('high', 0)), float(candle.get('low', 0)),
            float(candle.get('close', 0)), int(candle.get('volume', 0)))
    
    async def update_candles(self, symbol: str, new_candles: List[Dict[str, Any]]) -> bool:
        """
        Update or insert candle data using UPSERT.
        
        Args:
            symbol: Stock symbol
            new_candles: List of new or updated candles
            
        Returns:
            True if successful, False otherwise
        """
        if not new_candles:
            return True
            
        try:
            async with self.get_connection() as conn:
                for candle in new_candles:
                    await conn.execute("""
                        INSERT INTO candle_data 
                        (symbol, timestamp, date, time, open, high, low, close, volume)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (symbol, timestamp) 
                        DO UPDATE SET
                            date = EXCLUDED.date,
                            time = EXCLUDED.time,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume
                    """, symbol, candle.get('timestamp', 0), candle.get('date', ''),
                        candle.get('time', ''), float(candle.get('open', 0)),
                        float(candle.get('high', 0)), float(candle.get('low', 0)),
                        float(candle.get('close', 0)), int(candle.get('volume', 0)))
                
                # Update latest candle if needed
                if new_candles:
                    latest = max(new_candles, key=lambda x: x.get('timestamp', 0))
                    await self._update_latest_candle(conn, symbol, latest)
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update candles for {symbol}: {e}")
            return False
    
    # ============= Read Operations =============
    
    async def load_candles(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load candle data from TimescaleDB.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of candles to load (most recent)
            
        Returns:
            List of candle dictionaries or None if not found
        """
        try:
            async with self.get_connection() as conn:
                if limit:
                    query = """
                        SELECT timestamp, date, time, open, high, low, close, volume
                        FROM candle_data
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, symbol, limit)
                else:
                    query = """
                        SELECT timestamp, date, time, open, high, low, close, volume
                        FROM candle_data
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                    """
                    rows = await conn.fetch(query, symbol)
                
                if not rows:
                    return None
                
                # Convert to list of dictionaries
                candles = []
                for row in rows:
                    candles.append({
                        'timestamp': row['timestamp'],
                        'date': row['date'],
                        'time': row['time'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['volume'])
                    })
                
                # Reverse to get chronological order
                candles.reverse()
                return candles
                
        except Exception as e:
            logger.error(f"Failed to load candles for {symbol}: {e}")
            return None
    
    async def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest candle for a symbol from cache.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest candle dictionary or None if not found
        """
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT timestamp, date, time, open, high, low, close, volume
                    FROM latest_candles
                    WHERE symbol = $1
                """, symbol)
                
                if not row:
                    # Try to get from main table
                    row = await conn.fetchrow("""
                        SELECT timestamp, date, time, open, high, low, close, volume
                        FROM candle_data
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, symbol)
                
                if row:
                    return {
                        'timestamp': row['timestamp'],
                        'date': row['date'],
                        'time': row['time'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['volume'])
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get latest candle for {symbol}: {e}")
            return None
    
    async def get_all_symbols(self) -> List[str]:
        """
        Get list of all symbols in the database.
        
        Returns:
            List of symbol strings
        """
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT symbol 
                    FROM candle_data 
                    ORDER BY symbol
                """)
                
                return [row['symbol'] for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get all symbols: {e}")
            return []
    
    async def get_candles_between(self, symbol: str, 
                                 start_timestamp: int, 
                                 end_timestamp: int) -> Optional[List[Dict[str, Any]]]:
        """
        Get candles between two timestamps.
        
        Args:
            symbol: Stock symbol
            start_timestamp: Start timestamp (inclusive)
            end_timestamp: End timestamp (inclusive)
            
        Returns:
            List of candle dictionaries or None if not found
        """
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT timestamp, date, time, open, high, low, close, volume
                    FROM candle_data
                    WHERE symbol = $1 AND timestamp >= $2 AND timestamp <= $3
                    ORDER BY timestamp
                """, symbol, start_timestamp, end_timestamp)
                
                if not rows:
                    return None
                
                candles = []
                for row in rows:
                    candles.append({
                        'timestamp': row['timestamp'],
                        'date': row['date'],
                        'time': row['time'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['volume'])
                    })
                
                return candles
                
        except Exception as e:
            logger.error(f"Failed to get candles between timestamps for {symbol}: {e}")
            return None
    
    # ============= Indicator Operations =============
    
    async def save_indicators(self, symbol: str, timestamp: int, 
                            indicator_name: str, indicator_data: Dict[str, Any]) -> bool:
        """
        Save indicator data to database.
        
        Args:
            symbol: Stock symbol
            timestamp: Candle timestamp
            indicator_name: Name of the indicator
            indicator_data: Indicator values as dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO indicator_data 
                    (symbol, timestamp, indicator_name, indicator_data)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (symbol, timestamp, indicator_name) 
                    DO UPDATE SET
                        indicator_data = EXCLUDED.indicator_data
                """, symbol, timestamp, indicator_name, json.dumps(indicator_data))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to save indicators for {symbol}: {e}")
            return False
    
    async def load_indicators(self, symbol: str, indicator_name: str, 
                            limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load indicator data from database.
        
        Args:
            symbol: Stock symbol
            indicator_name: Name of the indicator
            limit: Maximum number of records to load
            
        Returns:
            List of indicator data or None if not found
        """
        try:
            async with self.get_connection() as conn:
                if limit:
                    query = """
                        SELECT timestamp, indicator_data
                        FROM indicator_data
                        WHERE symbol = $1 AND indicator_name = $2
                        ORDER BY timestamp DESC
                        LIMIT $3
                    """
                    rows = await conn.fetch(query, symbol, indicator_name, limit)
                else:
                    query = """
                        SELECT timestamp, indicator_data
                        FROM indicator_data
                        WHERE symbol = $1 AND indicator_name = $2
                        ORDER BY timestamp DESC
                    """
                    rows = await conn.fetch(query, symbol, indicator_name)
                
                if not rows:
                    return None
                
                indicators = []
                for row in rows:
                    data = json.loads(row['indicator_data'])
                    data['timestamp'] = row['timestamp']
                    indicators.append(data)
                
                # Reverse to get chronological order
                indicators.reverse()
                return indicators
                
        except Exception as e:
            logger.error(f"Failed to load indicators for {symbol}: {e}")
            return None
    
    # ============= Cleanup Operations =============
    
    async def cleanup_old_data(self, days_to_keep: int = 365) -> int:
        """
        Remove data older than specified days.
        
        Args:
            days_to_keep: Number of days of data to keep
            
        Returns:
            Number of records deleted
        """
        try:
            async with self.get_connection() as conn:
                # Calculate cutoff timestamp (milliseconds)
                cutoff_timestamp = int((datetime.now(timezone.utc).timestamp() - (days_to_keep * 86400)) * 1000)
                
                # Delete old candle data
                result = await conn.execute("""
                    DELETE FROM candle_data
                    WHERE timestamp < $1
                """, cutoff_timestamp)
                
                deleted_count = int(result.split()[-1])
                
                # Delete old indicator data
                await conn.execute("""
                    DELETE FROM indicator_data
                    WHERE timestamp < $1
                """, cutoff_timestamp)
                
                logger.info(f"Cleaned up {deleted_count} old records")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return 0
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.initialized = False
            logger.info("Database connection pool closed")

# Global instance
db_service = DatabaseService()