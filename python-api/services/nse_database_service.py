"""
NSE PostgreSQL Database Service for Stock Data Storage
Optimized for high-performance storage and retrieval of stock candle data
"""

import os
import json
import logging
import asyncio
import asyncpg
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import time

load_dotenv()

logger = logging.getLogger(__name__)

class NSEDatabaseService:
    """
    High-performance PostgreSQL service for NSE stock data.
    Optimized for storing and retrieving stock candle data with maximum performance.
    """
    
    def __init__(self):
        # Database connection parameters
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse',  # Using the NSE database as requested
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        }
        
        self.pool = None
        self.initialized = False
        self.initializing = False  # Prevent concurrent initialization
        self._init_lock = asyncio.Lock()  # Lock for initialization
        self.batch_size = 5000  # Optimal batch size for bulk inserts
        
    async def initialize(self):
        """Initialize database connection pool and create tables."""
        # Quick check without lock
        if self.initialized:
            return
        
        # Use lock to prevent concurrent initialization
        async with self._init_lock:
            # Double-check after acquiring lock
            if self.initialized:
                return
            
            if self.initializing:
                # Wait for ongoing initialization
                while self.initializing and not self.initialized:
                    await asyncio.sleep(0.1)
                return
            
            self.initializing = True
            
            try:
                # Close existing pool if it exists
                if self.pool:
                    try:
                        await self.pool.close()
                    except:
                        pass
                    self.pool = None
                
                # Create connection pool with optimized settings
                self.pool = await asyncpg.create_pool(
                    **self.db_config,
                    min_size=2,  # Reduced to avoid connection exhaustion
                    max_size=10,   # Reduced max connections
                    max_queries=50000,
                    max_inactive_connection_lifetime=30,
                    command_timeout=30,
                    connection_class=asyncpg.Connection,
                    setup=self._setup_connection,
                    server_settings={
                        'application_name': 'nse_data_service',
                        'jit': 'off'
                    }
                )
                
                # Create tables if they don't exist
                await self._create_tables()
                
                self.initialized = True
                self.initializing = False
                logger.info("NSE Database service initialized successfully")
                
            except Exception as e:
                self.initializing = False
                logger.error(f"Failed to initialize NSE database: {e}")
                # Don't raise - allow fallback to file storage
                self.initialized = False
    
    async def _setup_connection(self, connection):
        """Setup each connection in the pool."""
        # Set statement timeout to prevent hanging queries
        await connection.execute("SET statement_timeout = '20s'")
        await connection.execute("SET idle_in_transaction_session_timeout = '10s'")
        await connection.execute("SET lock_timeout = '5s'")
    
    async def health_check(self) -> bool:
        """Perform a health check on the database connection."""
        if not self.initialized or not self.pool:
            return False
        
        try:
            async with asyncio.timeout(3):
                async with self.pool.acquire() as conn:
                    result = await conn.fetchval("SELECT 1")
                    return result == 1
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def _create_tables(self):
        """Create optimized PostgreSQL tables for stock data."""
        async with self.pool.acquire() as conn:
            # Main candle data table with partitioning support
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_candles (
                    symbol VARCHAR(50) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume DOUBLE PRECISION,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, timestamp)
                );
            """)
            
            # Create indexes for fast queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_symbol 
                ON stock_candles (symbol);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_timestamp 
                ON stock_candles (timestamp DESC);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_symbol_timestamp 
                ON stock_candles (symbol, timestamp DESC);
            """)
            
            # Table for latest candle cache (for fast latest price queries)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS latest_candles (
                    symbol VARCHAR(50) PRIMARY KEY,
                    timestamp BIGINT NOT NULL,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume DOUBLE PRECISION,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table for stock metadata
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_metadata (
                    symbol VARCHAR(50) PRIMARY KEY,
                    total_candles INTEGER,
                    first_timestamp BIGINT,
                    last_timestamp BIGINT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table for precalculated indicators
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS precalculated_indicators (
                    symbol VARCHAR(50) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    indicator_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, timestamp)
                );
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_precalc_symbol 
                ON precalculated_indicators (symbol);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_precalc_timestamp 
                ON precalculated_indicators (timestamp DESC);
            """)
            
            # Create a function to update the updated_at timestamp
            await conn.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)
            
            # Create trigger for auto-updating timestamps
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_stock_candles_updated_at') THEN
                        CREATE TRIGGER update_stock_candles_updated_at 
                        BEFORE UPDATE ON stock_candles 
                        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                    END IF;
                END$$;
            """)
            
            logger.info("NSE Database tables created successfully")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool with health check."""
        if not self.initialized:
            await self.initialize()
        
        if not self.pool:
            raise Exception("Database pool not available")
        
        conn = None
        retries = 3
        for attempt in range(retries):
            try:
                conn = await asyncio.wait_for(self.pool.acquire(), timeout=5.0)
                # Health check
                await conn.fetchval("SELECT 1")
                yield conn
                break
            except asyncio.TimeoutError:
                logger.error(f"Timeout acquiring database connection (attempt {attempt + 1}/{retries})")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(0.5)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                logger.warning(f"Connection error (attempt {attempt + 1}/{retries}): {e}")
                if conn:
                    try:
                        await self.pool.release(conn, timeout=1.0)
                    except:
                        pass
                    conn = None
                if attempt == retries - 1:
                    # Reset pool on persistent connection errors
                    self.initialized = False
                    raise
                await asyncio.sleep(0.5)
            finally:
                if conn:
                    try:
                        await self.pool.release(conn, timeout=2.0)
                    except Exception as e:
                        logger.warning(f"Error releasing connection: {e}")
    
    # ============= Write Operations =============
    
    async def save_candles(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """
        Save stock candle data to PostgreSQL using optimized bulk insert.
        
        Args:
            symbol: Stock symbol
            candles: List of candle dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        # Ensure database is initialized
        if not self.initialized:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize database for save_candles: {e}")
                return False
        
        if not self.initialized:
            logger.warning(f"Database not initialized, cannot save {symbol}")
            return False
            
        return await self.save_stock_data(symbol, candles)
    
    async def save_stock_data(self, symbol: str, candles: List[Dict[str, Any]]) -> bool:
        """
        Save stock candle data to PostgreSQL using optimized bulk insert.
        
        Args:
            symbol: Stock symbol
            candles: List of candle dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not candles:
            return True
            
        max_retries = 2
        for retry in range(max_retries):
            try:
                # Check pool health
                if self.pool is None or self.pool.is_closing():
                    logger.warning("Connection pool is not available, reinitializing...")
                    self.initialized = False
                    await self.initialize()
                    
                async with self.get_connection() as conn:
                    # Prepare data for bulk insert
                    values = []
                    for candle in candles:
                        values.append((
                            symbol,
                            candle.get('timestamp', 0),
                            float(candle.get('open', 0)),
                            float(candle.get('high', 0)),
                            float(candle.get('low', 0)),
                            float(candle.get('close', 0)),
                            float(candle.get('volume', 0))
                        ))
                    
                    # Use COPY for fastest bulk insert
                    await conn.copy_records_to_table(
                        'stock_candles',
                        records=values,
                        columns=['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
                    )
                    
                    # Update latest candle cache
                    if candles:
                        latest = max(candles, key=lambda x: x.get('timestamp', 0))
                        await self._update_latest_candle(conn, symbol, latest)
                    
                    # Update metadata
                    await self._update_metadata(conn, symbol, candles)
                    
                    logger.debug(f"Saved {len(candles)} candles for {symbol}")
                    return True
                    
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError) as e:
                # Connection pool issue
                logger.error(f"Connection pool error for {symbol} (retry {retry + 1}/{max_retries}): {e}")
                self.initialized = False
                if retry < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return False
            except asyncpg.UniqueViolationError:
                # Duplicate data - not an error
                logger.debug(f"Duplicate data for {symbol}, skipping")
                return True
            except asyncpg.PostgresError as e:
                # Database-specific error
                logger.error(f"PostgreSQL error for {symbol}: {e}")
                return False
            except Exception as e:
                logger.error(f"Failed to save stock data for {symbol}: {e}")
                return False
        
        return False
    
    async def save_stock_data_batch(self, stock_data_list: List[Tuple[str, List[Dict]]]) -> Dict[str, bool]:
        """
        Save multiple stocks' data in a single transaction for maximum performance.
        
        Args:
            stock_data_list: List of (symbol, candles) tuples
            
        Returns:
            Dictionary mapping symbols to success status
        """
        results = {}
        
        try:
            async with self.get_connection() as conn:
                # Start transaction
                async with conn.transaction():
                    # Prepare all data for bulk insert
                    all_values = []
                    latest_candles = []
                    metadata_updates = []
                    
                    for symbol, candles in stock_data_list:
                        if not candles:
                            results[symbol] = True
                            continue
                        
                        # Prepare candle data
                        for candle in candles:
                            all_values.append((
                                symbol,
                                candle.get('timestamp', 0),
                                float(candle.get('open', 0)),
                                float(candle.get('high', 0)),
                                float(candle.get('low', 0)),
                                float(candle.get('close', 0)),
                                float(candle.get('volume', 0))
                            ))
                        
                        # Track latest candle
                        latest = max(candles, key=lambda x: x.get('timestamp', 0))
                        latest_candles.append((symbol, latest))
                        
                        # Track metadata
                        metadata_updates.append((symbol, candles))
                        results[symbol] = True
                    
                    # Bulk insert all candles
                    if all_values:
                        await conn.copy_records_to_table(
                            'stock_candles',
                            records=all_values,
                            columns=['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
                        )
                    
                    # Update all latest candles
                    for symbol, latest in latest_candles:
                        await self._update_latest_candle(conn, symbol, latest)
                    
                    # Update all metadata
                    for symbol, candles in metadata_updates:
                        await self._update_metadata(conn, symbol, candles)
                    
                logger.info(f"Batch saved data for {len(stock_data_list)} stocks")
                
        except Exception as e:
            logger.error(f"Failed to batch save stock data: {e}")
            for symbol, _ in stock_data_list:
                results[symbol] = False
        
        return results
    
    async def update_or_insert_candles(self, symbol: str, new_candles: List[Dict[str, Any]]) -> bool:
        """
        Update existing candles or insert new ones using UPSERT.
        
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
                # Use ON CONFLICT for upsert
                for candle in new_candles:
                    await conn.execute("""
                        INSERT INTO stock_candles 
                        (symbol, timestamp, open, high, low, close, volume)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (symbol, timestamp) 
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            updated_at = CURRENT_TIMESTAMP
                    """, symbol, candle.get('timestamp', 0),
                        float(candle.get('open', 0)),
                        float(candle.get('high', 0)),
                        float(candle.get('low', 0)),
                        float(candle.get('close', 0)),
                        float(candle.get('volume', 0)))
                
                # Update latest candle if needed
                if new_candles:
                    latest = max(new_candles, key=lambda x: x.get('timestamp', 0))
                    await self._update_latest_candle(conn, symbol, latest)
                    await self._update_metadata(conn, symbol, new_candles)
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update candles for {symbol}: {e}")
            return False
    
    async def _update_latest_candle(self, conn, symbol: str, candle: Dict[str, Any]):
        """Update the latest candle cache for a symbol."""
        await conn.execute("""
            INSERT INTO latest_candles 
            (symbol, timestamp, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (symbol) 
            DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                updated_at = CURRENT_TIMESTAMP
        """, symbol, candle.get('timestamp', 0),
            float(candle.get('open', 0)),
            float(candle.get('high', 0)),
            float(candle.get('low', 0)),
            float(candle.get('close', 0)),
            float(candle.get('volume', 0)))
    
    async def _update_metadata(self, conn, symbol: str, candles: List[Dict[str, Any]]):
        """Update stock metadata."""
        if not candles:
            return
        
        timestamps = [c.get('timestamp', 0) for c in candles]
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        
        await conn.execute("""
            INSERT INTO stock_metadata 
            (symbol, total_candles, first_timestamp, last_timestamp)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (symbol) 
            DO UPDATE SET
                total_candles = stock_metadata.total_candles + EXCLUDED.total_candles,
                first_timestamp = LEAST(stock_metadata.first_timestamp, EXCLUDED.first_timestamp),
                last_timestamp = GREATEST(stock_metadata.last_timestamp, EXCLUDED.last_timestamp),
                last_updated = CURRENT_TIMESTAMP
        """, symbol, len(candles), first_ts, last_ts)
    
    # ============= Read Operations =============
    
    async def load_candles(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load stock candle data from PostgreSQL.
        
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
                        SELECT timestamp, open, high, low, close, volume
                        FROM stock_candles
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, symbol, limit)
                else:
                    query = """
                        SELECT timestamp, open, high, low, close, volume
                        FROM stock_candles
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
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume'])
                    })
                
                # Reverse to get chronological order
                candles.reverse()
                return candles
                
        except Exception as e:
            logger.error(f"Failed to load stock data for {symbol}: {e}")
            return None
    
    async def load_stock_data(self, symbol: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Alias for load_candles for compatibility.
        """
        return await self.load_candles(symbol, limit)
    
    async def load_multiple_stocks(self, symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load data for multiple stocks efficiently in parallel.
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary mapping symbols to candle data
        """
        results = {}
        
        try:
            # Create tasks for parallel loading
            tasks = []
            for symbol in symbols:
                tasks.append(self.load_stock_data(symbol))
            
            # Execute all tasks in parallel
            candle_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Map results
            for symbol, candles in zip(symbols, candle_results):
                if isinstance(candles, Exception):
                    logger.error(f"Error loading {symbol}: {candles}")
                    results[symbol] = None
                else:
                    results[symbol] = candles
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to load multiple stocks: {e}")
            return {symbol: None for symbol in symbols}
    
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
                    SELECT timestamp, open, high, low, close, volume
                    FROM latest_candles
                    WHERE symbol = $1
                """, symbol)
                
                if not row:
                    # Try to get from main table
                    row = await conn.fetchrow("""
                        SELECT timestamp, open, high, low, close, volume
                        FROM stock_candles
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, symbol)
                
                if row:
                    return {
                        'timestamp': row['timestamp'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume'])
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
                    FROM stock_candles 
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
                    SELECT timestamp, open, high, low, close, volume
                    FROM stock_candles
                    WHERE symbol = $1 AND timestamp >= $2 AND timestamp <= $3
                    ORDER BY timestamp
                """, symbol, start_timestamp, end_timestamp)
                
                if not rows:
                    return None
                
                candles = []
                for row in rows:
                    candles.append({
                        'timestamp': row['timestamp'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume'])
                    })
                
                return candles
                
        except Exception as e:
            logger.error(f"Failed to get candles between timestamps for {symbol}: {e}")
            return None
    
    # ============= Precalculated Indicators =============
    
    async def save_precalculated_indicators(self, symbol: str, timestamp: int, 
                                          indicators: Dict[str, Any]) -> bool:
        """
        Save precalculated indicators for a symbol and timestamp.
        
        Args:
            symbol: Stock symbol
            timestamp: Candle timestamp
            indicators: Dictionary of indicator values
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO precalculated_indicators 
                    (symbol, timestamp, indicator_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (symbol, timestamp) 
                    DO UPDATE SET
                        indicator_data = EXCLUDED.indicator_data
                """, symbol, timestamp, json.dumps(indicators))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to save precalculated indicators for {symbol}: {e}")
            return False
    
    async def load_precalculated_indicators(self, symbol: str, 
                                          limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Load precalculated indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of records to load
            
        Returns:
            List of indicator data or None if not found
        """
        try:
            async with self.get_connection() as conn:
                if limit:
                    query = """
                        SELECT timestamp, indicator_data
                        FROM precalculated_indicators
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, symbol, limit)
                else:
                    query = """
                        SELECT timestamp, indicator_data
                        FROM precalculated_indicators
                        WHERE symbol = $1
                        ORDER BY timestamp DESC
                    """
                    rows = await conn.fetch(query, symbol)
                
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
            logger.error(f"Failed to load precalculated indicators for {symbol}: {e}")
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
                    DELETE FROM stock_candles
                    WHERE timestamp < $1
                """, cutoff_timestamp)
                
                deleted_count = int(result.split()[-1])
                
                # Delete old indicator data
                await conn.execute("""
                    DELETE FROM precalculated_indicators
                    WHERE timestamp < $1
                """, cutoff_timestamp)
                
                logger.info(f"Cleaned up {deleted_count} old records")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return 0
    
    async def delete_all_data(self) -> bool:
        """
        Delete all data from all tables (use with caution).
        
        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("TRUNCATE TABLE stock_candles CASCADE")
                await conn.execute("TRUNCATE TABLE latest_candles CASCADE")
                await conn.execute("TRUNCATE TABLE stock_metadata CASCADE")
                await conn.execute("TRUNCATE TABLE precalculated_indicators CASCADE")
                
                logger.info("All data deleted from NSE database")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete all data: {e}")
            return False
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            async with self.get_connection() as conn:
                # Get total records
                candle_count = await conn.fetchval("SELECT COUNT(*) FROM stock_candles")
                symbol_count = await conn.fetchval("SELECT COUNT(DISTINCT symbol) FROM stock_candles")
                
                # Get database size
                db_size = await conn.fetchval("""
                    SELECT pg_database_size('nse')
                """)
                
                # Get table sizes
                candles_size = await conn.fetchval("""
                    SELECT pg_total_relation_size('stock_candles')
                """)
                
                indicators_size = await conn.fetchval("""
                    SELECT pg_total_relation_size('precalculated_indicators')
                """)
                
                return {
                    'total_candles': candle_count,
                    'total_symbols': symbol_count,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'candles_table_size_mb': round(candles_size / (1024 * 1024), 2),
                    'indicators_table_size_mb': round(indicators_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.initialized = False
            logger.info("NSE Database connection pool closed")

# Global instance
nse_db_service = NSEDatabaseService()