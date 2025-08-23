"""
Ultra-Fast Unified Database Service
- Single database for all stock data (OHLCV + indicators)
- Composite key system for O(1) lookups (SYMBOL_KEY format)
- Streaming chunk-based storage
- Maximum parallelization support
"""

import os
import asyncio
import asyncpg
import json
import logging
import psutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import hashlib

load_dotenv()
logger = logging.getLogger(__name__)

class UltraFastDatabaseService:
    """
    Ultra-fast unified database service with composite key system.
    Eliminates NSE database - everything goes to one optimized database.
    """
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',  # Use existing database with new structure
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        self.pool = None
        self.initialized = False
        self._init_lock = asyncio.Lock()
        
        # Dynamic resource allocation based on system capabilities
        self.max_connections = min(psutil.cpu_count() * 4, 100)
        self.chunk_size = 500  # Process in chunks for memory efficiency
        
        # Connection pool for high-concurrency operations
        self.pool_config = {
            'min_size': 10,
            'max_size': self.max_connections,
            'max_queries': 100000,
            'max_inactive_connection_lifetime': 30,
            'command_timeout': 30
        }

    async def initialize(self):
        """Initialize ultra-fast database with optimized settings"""
        if self.initialized:
            return
        
        async with self._init_lock:
            if self.initialized:
                return
                
            try:
                # Create database if not exists
                await self._create_database_if_not_exists()
                
                # Create optimized connection pool
                self.pool = await asyncpg.create_pool(
                    **self.db_config,
                    **self.pool_config,
                    setup=self._setup_connection,
                    server_settings={
                        'application_name': 'ultra_fast_stocks_service',
                        'jit': 'off'
                    }
                )
                
                # Create unified table structure
                await self._create_unified_tables()
                
                self.initialized = True
                logger.info(f"🚀 Ultra-fast database initialized with {self.max_connections} max connections")
                
            except Exception as e:
                logger.error(f"Failed to initialize ultra-fast database: {e}")
                raise

    async def _create_database_if_not_exists(self):
        """Ensure the database exists (nse_highspeed should already exist)"""
        try:
            # Connect to default postgres database
            conn = await asyncpg.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database='postgres',
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            
            # Check if database exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                self.db_config['database']
            )
            
            if not exists:
                await conn.execute(f"CREATE DATABASE {self.db_config['database']}")
                logger.info(f"Created database: {self.db_config['database']}")
            else:
                logger.info(f"Database {self.db_config['database']} already exists")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"Error checking database: {e}")
            raise

    async def _setup_connection(self, connection):
        """Setup each connection for maximum performance"""
        try:
            # Session-level settings (can be changed without restart)
            await connection.execute("SET statement_timeout = '30s'")
            await connection.execute("SET idle_in_transaction_session_timeout = '10s'")
            await connection.execute("SET lock_timeout = '5s'")
            
            # Performance settings that don't require restart
            await connection.execute("SET synchronous_commit = off")
            await connection.execute("SET work_mem = '64MB'")
            await connection.execute("SET maintenance_work_mem = '256MB'")
            
            # Skip server-level settings that require restart
            # These would be set in postgresql.conf:
            # - wal_buffers = 16MB
            # - shared_buffers = 256MB
            
        except Exception as e:
            # Don't fail if some settings can't be applied
            logger.warning(f"Some connection settings could not be applied: {e}")
            logger.info("Consider updating postgresql.conf for optimal performance")
    
    async def _check_if_migration_needed(self, conn):
        """Check if database needs migration to composite key system"""
        try:
            # Check if daily_candles has the new structure
            columns = await conn.fetch("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'daily_candles'
                ORDER BY ordinal_position
            """)
            
            column_names = [col['column_name'] for col in columns]
            
            # Check for new structure (candle_key_id primary key)
            has_composite_key = 'candle_key_id' in column_names
            has_sequence_number = 'candle_sequence_number' in column_names
            
            # Check current primary key
            primary_keys = await conn.fetch("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'daily_candles'::regclass AND i.indisprimary
            """)
            
            current_pk = [pk['attname'] for pk in primary_keys]
            
            # Migration needed if we don't have composite key structure
            migration_needed = not (has_composite_key and has_sequence_number)
            
            if migration_needed:
                logger.info(f"Current columns: {column_names}")
                logger.info(f"Current primary key: {current_pk}")
                logger.info("Need migration to: candle_key_id, symbol, candle_sequence_number")
            
            return migration_needed
            
        except Exception as e:
            logger.error(f"Error checking migration status: {e}")
            return True  # Assume migration needed if we can't check

    async def _check_tables_exist(self, conn):
        """Check if main tables exist"""
        try:
            tables = await conn.fetch("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename IN ('daily_candles', 'weekly_candles', 'monthly_candles')
            """)
            
            table_names = [t['tablename'] for t in tables]
            return 'daily_candles' in table_names
            
        except Exception as e:
            logger.error(f"Error checking if tables exist: {e}")
            return False

    async def _create_new_structure(self, conn):
        """Create brand new structure with composite keys"""
        try:
            # Create daily candles table with new structure
            await conn.execute("""
                CREATE TABLE daily_candles (
                    candle_key_id VARCHAR(50) PRIMARY KEY,       -- "20MICRONS_1", "20MICRONS_2" 
                    symbol VARCHAR(20) NOT NULL,                 -- "20MICRONS"
                    candle_sequence_number INTEGER NOT NULL,     -- 0, 1, 2, 3...
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    indicators JSONB DEFAULT '{}',               -- All indicators in JSONB
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create weekly candles table
            await conn.execute("""
                CREATE TABLE weekly_candles (
                    candle_key_id VARCHAR(50) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    candle_sequence_number INTEGER NOT NULL,
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    indicators JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create monthly candles table
            await conn.execute("""
                CREATE TABLE monthly_candles (
                    candle_key_id VARCHAR(50) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    candle_sequence_number INTEGER NOT NULL,
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    indicators JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create symbol metadata table for tracking latest keys
            await conn.execute("""
                CREATE TABLE symbol_latest_keys (
                    symbol VARCHAR(20) PRIMARY KEY,
                    latest_daily_key INTEGER DEFAULT -1,        -- Start at -1 so first key becomes 0
                    latest_weekly_key INTEGER DEFAULT -1,
                    latest_monthly_key INTEGER DEFAULT -1,
                    total_daily_candles INTEGER DEFAULT 0,
                    total_weekly_candles INTEGER DEFAULT 0,
                    total_monthly_candles INTEGER DEFAULT 0,
                    first_timestamp BIGINT,
                    latest_timestamp BIGINT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create optimized indexes
            await self._create_performance_indexes(conn)
            
            logger.info("✅ Created new ultra-fast database structure with composite keys")
            logger.info("✅ Primary keys: candle_key_id (SYMBOL_123 format)")
            logger.info("✅ Metadata table: symbol_latest_keys for key tracking")
            
        except Exception as e:
            logger.error(f"Failed to create new structure: {e}")
            raise

    async def _create_unified_tables(self):
        """Create or update tables with composite key system"""
        async with self.pool.acquire() as conn:
            
            # Check if tables exist
            tables_exist = await self._check_tables_exist(conn)
            
            if not tables_exist:
                logger.info("🏗️ Creating new ultra-fast database structure with composite keys")
                await self._create_new_structure(conn)
                return
            
            # Check if migration is needed for existing tables
            migration_needed = await self._check_if_migration_needed(conn)
            
            if migration_needed:
                logger.warning("Existing database needs migration to composite key system!")
                logger.warning("Please run: python migrate_database.py")
                logger.warning("Current structure uses (symbol, timestamp) primary key")
                logger.warning("New structure needs candle_key_id primary key (SYMBOL_123 format)")
                logger.warning("System will work with reduced performance until migration is complete")
                
                # Create the symbol_latest_keys table even with old structure
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS symbol_latest_keys (
                        symbol VARCHAR(20) PRIMARY KEY,
                        latest_daily_key INTEGER DEFAULT -1,
                        latest_weekly_key INTEGER DEFAULT -1,
                        latest_monthly_key INTEGER DEFAULT -1,
                        total_daily_candles INTEGER DEFAULT 0,
                        total_weekly_candles INTEGER DEFAULT 0,
                        total_monthly_candles INTEGER DEFAULT 0,
                        first_timestamp BIGINT,
                        latest_timestamp BIGINT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                logger.info("✅ Created symbol_latest_keys table for old structure compatibility")
                return
            
            # Tables exist and are properly migrated
            logger.info("✅ Database structure is up to date with composite key system")
            
            # Symbol metadata for key management
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbol_metadata (
                    symbol VARCHAR(20) PRIMARY KEY,
                    latest_key INTEGER NOT NULL DEFAULT 0,   -- Current max key for this symbol
                    total_candles INTEGER NOT NULL DEFAULT 0,
                    first_timestamp BIGINT,
                    last_timestamp BIGINT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Weekly candles table (same structure)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_candles (
                    composite_key VARCHAR(50) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    key_number INTEGER NOT NULL,
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    indicators JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Monthly candles table (same structure)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_candles (
                    composite_key VARCHAR(50) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    key_number INTEGER NOT NULL,
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    indicators JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create performance indexes
            await self._create_performance_indexes(conn)
            
            logger.info("✅ Created unified table structure with composite keys")
    
    async def _create_optimized_tables(self):
        """Alias for _create_unified_tables for backward compatibility"""
        return await self._create_unified_tables()
    
    async def _create_speed_indexes(self):
        """Alias for _create_performance_indexes for backward compatibility"""
        async with self.pool.acquire() as conn:
            return await self._create_performance_indexes(conn)

    async def _create_performance_indexes(self, conn):
        """Create indexes for maximum query performance"""
        
        # Indexes for daily_candles
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_symbol_key 
            ON daily_candles(symbol, candle_sequence_number DESC)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_timestamp 
            ON daily_candles(timestamp DESC)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_indicators 
            ON daily_candles USING GIN (indicators)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_symbol_timestamp 
            ON daily_candles(symbol, timestamp DESC)
        """)
        
        # Same indexes for weekly and monthly
        for timeframe in ['weekly', 'monthly']:
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_key 
                ON {timeframe}_candles(symbol, candle_sequence_number DESC)
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{timeframe}_timestamp 
                ON {timeframe}_candles(timestamp DESC)
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{timeframe}_indicators 
                ON {timeframe}_candles USING GIN (indicators)
            """)

    async def get_next_key_batch(self, symbol: str, batch_size: int, timeframe: str = 'daily') -> int:
        """Get the next batch of keys for a symbol (thread-safe)"""
        async with self.pool.acquire() as conn:
            # Use the new symbol_latest_keys table
            timeframe_key_col = f'latest_{timeframe}_key'
            timeframe_count_col = f'total_{timeframe}_candles'
            
            # Atomic increment to get next key batch
            result = await conn.fetchrow(f"""
                INSERT INTO symbol_latest_keys (symbol, {timeframe_key_col}, {timeframe_count_col})
                VALUES ($1, $2, $2)
                ON CONFLICT (symbol) 
                DO UPDATE SET
                    {timeframe_key_col} = symbol_latest_keys.{timeframe_key_col} + $2,
                    {timeframe_count_col} = symbol_latest_keys.{timeframe_count_col} + $2,
                    last_updated = CURRENT_TIMESTAMP
                RETURNING {timeframe_key_col} - $2 as start_key
            """, symbol, batch_size)
            
            return result['start_key']

    async def store_chunk_with_indicators(self, symbol: str, chunk_data: List[Dict], 
                                        timeframe: str = 'daily') -> bool:
        """
        Store a chunk of processed data with indicators using new composite key structure.
        This enables streaming processing without waiting for entire stock completion.
        """
        if not chunk_data:
            return True
        
        try:
            # Get next key batch for this chunk
            start_key = await self.get_next_key_batch(symbol, len(chunk_data), timeframe)
            
            # Prepare data with composite keys using new structure
            values = []
            for i, candle in enumerate(chunk_data):
                sequence_number = start_key + i
                candle_key_id = f"{symbol}_{sequence_number}"  # New composite primary key
                
                # Handle both dict and string data formats
                if isinstance(candle, str):
                    logger.warning(f"Skipping string data for {symbol}: {candle}")
                    continue
                elif not isinstance(candle, dict):
                    logger.warning(f"Skipping invalid data type for {symbol}: {type(candle)}")
                    continue
                
                # Extract OHLCV data
                ohlcv_data = [
                    candle_key_id,                           # candle_key_id (PRIMARY KEY)
                    symbol,                                  # symbol
                    sequence_number,                         # candle_sequence_number
                    candle.get('timestamp', 0),             # timestamp
                    datetime.fromtimestamp(candle.get('timestamp', 0) / 1000),  # datetime (timezone-naive)
                    float(candle.get('open', 0)),           # open
                    float(candle.get('high', 0)),           # high
                    float(candle.get('low', 0)),            # low
                    float(candle.get('close', 0)),          # close
                    int(candle.get('volume', 0))            # volume
                ]
                
                # Extract all indicators into JSONB
                indicators = {}
                for key, value in candle.items():
                    if key not in ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume']:
                        if value is not None:
                            indicators[key] = float(value) if isinstance(value, (int, float)) else value
                
                ohlcv_data.append(json.dumps(indicators))   # indicators JSONB
                values.append(tuple(ohlcv_data))
            
            # Bulk insert chunk using new table structure
            table_name = f"{timeframe}_candles"
            async with self.pool.acquire() as conn:
                await conn.executemany(f"""
                    INSERT INTO {table_name} 
                    (candle_key_id, symbol, candle_sequence_number, timestamp, datetime, 
                     open, high, low, close, volume, indicators)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (candle_key_id) 
                    DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        datetime = EXCLUDED.datetime,
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        indicators = EXCLUDED.indicators,
                        updated_at = CURRENT_TIMESTAMP
                """, values)
            
            logger.debug(f"✅ Stored chunk of {len(chunk_data)} candles for {symbol} (keys {start_key}-{start_key + len(chunk_data) - 1})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store chunk for {symbol}: {e}")
            return False

    async def get_candle_by_key(self, symbol: str, key_number: int, 
                               timeframe: str = 'daily') -> Optional[Dict]:
        """Get specific candle by symbol and key number (O(1) lookup)"""
        try:
            composite_key = f"{symbol}_{key_number}"
            table_name = f"{timeframe}_candles"
            
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(f"""
                    SELECT * FROM {table_name} WHERE composite_key = $1
                """, composite_key)
                
                if row:
                    result = dict(row)
                    # Parse indicators from JSONB
                    if result.get('indicators'):
                        indicators = json.loads(result['indicators']) if isinstance(result['indicators'], str) else result['indicators']
                        result.update(indicators)
                    return result
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get candle {symbol}_{key_number}: {e}")
            return None

    async def get_last_n_candles(self, symbol: str, n: int, 
                                timeframe: str = 'daily') -> List[Dict]:
        """Get last N candles for a symbol (optimized with composite keys)"""
        try:
            async with self.pool.acquire() as conn:
                # Get current latest key for symbol
                latest_key = await conn.fetchval("""
                    SELECT latest_key FROM symbol_metadata WHERE symbol = $1
                """, symbol)
                
                if latest_key is None:
                    return []
                
                # Generate composite keys for last N candles
                start_key = max(0, latest_key - n)
                composite_keys = [f"{symbol}_{i}" for i in range(start_key, latest_key)]
                
                if not composite_keys:
                    return []
                
                table_name = f"{timeframe}_candles"
                rows = await conn.fetch(f"""
                    SELECT * FROM {table_name} 
                    WHERE composite_key = ANY($1)
                    ORDER BY key_number ASC
                """, composite_keys)
                
                results = []
                for row in rows:
                    result = dict(row)
                    # Parse indicators from JSONB
                    if result.get('indicators'):
                        indicators = json.loads(result['indicators']) if isinstance(result['indicators'], str) else result['indicators']
                        result.update(indicators)
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get last {n} candles for {symbol}: {e}")
            return []

    async def get_candle_n_days_ago(self, symbol: str, days_ago: int, 
                                   timeframe: str = 'daily') -> Optional[Dict]:
        """Get candle from N days ago (O(1) lookup with composite key)"""
        try:
            async with self.pool.acquire() as conn:
                # Get current latest key
                latest_key = await conn.fetchval("""
                    SELECT latest_key FROM symbol_metadata WHERE symbol = $1
                """, symbol)
                
                if latest_key is None or latest_key < days_ago:
                    return None
                
                # Calculate target key (latest - days_ago)
                target_key = latest_key - days_ago
                composite_key = f"{symbol}_{target_key}"
                
                return await self.get_candle_by_key(symbol, target_key, timeframe)
                
        except Exception as e:
            logger.error(f"Failed to get {days_ago} days ago candle for {symbol}: {e}")
            return None

    async def query_by_indicators(self, indicator_conditions: List[Dict], 
                                 symbols: List[str] = None,
                                 timeframe: str = 'daily') -> List[Dict]:
        """
        Query stocks by indicator conditions using JSONB indexes.
        Example: [{'name': 'rsi_14', 'operator': '>', 'value': 70}]
        """
        try:
            async with self.pool.acquire() as conn:
                # Build dynamic query
                where_conditions = []
                params = []
                param_counter = 1
                
                for condition in indicator_conditions:
                    indicator_name = condition['name']
                    operator = condition['operator']
                    value = condition['value']
                    
                    where_conditions.append(f"(indicators->>'{indicator_name}')::numeric {operator} ${param_counter}")
                    params.append(value)
                    param_counter += 1
                
                # Add symbol filter if provided
                if symbols:
                    where_conditions.append(f"symbol = ANY(${param_counter})")
                    params.append(symbols)
                
                # Get latest data for each symbol
                table_name = f"{timeframe}_candles"
                query = f"""
                    SELECT DISTINCT ON (symbol) *
                    FROM {table_name}
                    WHERE {' AND '.join(where_conditions)}
                    ORDER BY symbol, key_number DESC
                """
                
                rows = await conn.fetch(query, *params)
                
                results = []
                for row in rows:
                    result = dict(row)
                    # Parse indicators from JSONB
                    if result.get('indicators'):
                        indicators = json.loads(result['indicators']) if isinstance(result['indicators'], str) else result['indicators']
                        result.update(indicators)
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to query by indicators: {e}")
            return []

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Get basic stats
                daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
                weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles") or 0
                monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles") or 0
                symbol_count = await conn.fetchval("SELECT COUNT(*) FROM symbol_metadata")
                
                # Get database size
                db_size = await conn.fetchval(f"""
                    SELECT pg_database_size('{self.db_config['database']}')
                """)
                
                return {
                    'total_daily_candles': daily_count,
                    'total_weekly_candles': weekly_count,
                    'total_monthly_candles': monthly_count,
                    'total_symbols': symbol_count,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'max_connections': self.max_connections,
                    'chunk_size': self.chunk_size
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}

    async def health_check(self) -> bool:
        """Comprehensive health check"""
        if not self.initialized or not self.pool:
            return False
        
        try:
            async with asyncio.timeout(5):
                async with self.pool.acquire() as conn:
                    result = await conn.fetchval("SELECT 1")
                    return result == 1
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    async def populate_from_nse_database(self) -> Dict[str, int]:
        """
        Compatibility method for populate_from_nse_database.
        Returns counts of processed data.
        """
        try:
            # Since we're using direct API fetching, return empty counts
            # This method exists for backward compatibility with hard refresh process
            return {
                'daily_inserted': 0,
                'weekly_inserted': 0, 
                'monthly_inserted': 0,
                'total_symbols': 0,
                'total_candles': 0,
                'successful': 0,
                'failed': 0,
                'total_stocks': 0
            }
        except Exception as e:
            logger.error(f"Error in populate_from_nse_database: {e}")
            return {
                'daily_inserted': 0,
                'weekly_inserted': 0,
                'monthly_inserted': 0, 
                'total_symbols': 0,
                'total_candles': 0,
                'successful': 0,
                'failed': 0,
                'total_stocks': 0
            }

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        async with self.pool.acquire() as conn:
            yield conn

    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            self.initialized = False
            logger.info("Ultra-fast database connection pool closed")

# Global instance
ultra_fast_db = UltraFastDatabaseService()