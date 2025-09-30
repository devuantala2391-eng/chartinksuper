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
import time
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
            'database': os.getenv('POSTGRES_DB', 'nse_highspeed'),  # Use database from environment
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        self.pool = None
        self.initialized = False
        self._init_lock = asyncio.Lock()
        
        # Dynamic resource allocation based on system capabilities
        self.max_connections = min(psutil.cpu_count() * 4, 100)
        self.chunk_size = 500  # Process in chunks for memory efficiency
        
        # For compatibility with query system - ultra-fast uses pure JSONB (no static indicators)
        self.static_indicators = set()  # Empty set - all indicators are in JSONB
        
        # Connection pool for high-concurrency operations
        self.pool_config = {
            'min_size': 10,
            'max_size': self.max_connections,
            'max_queries': 100000,
            'max_inactive_connection_lifetime': 30,
            'command_timeout': 30
        }

    def _extract_bollinger_bands_fields(self, indicators: dict) -> dict:
        """Extract individual Bollinger Bands fields from JSON structure"""
        extracted = {}

        # Look for Bollinger Bands indicators in the format: daily_bb_20_2, weekly_bb_20_2, etc.
        for key, value in indicators.items():
            if isinstance(value, dict) and ('upper' in value and 'middle' in value and 'lower' in value):
                # This is a Bollinger Bands indicator - extract individual fields
                extracted[f"{key}_upper"] = value.get('upper')
                extracted[f"{key}_middle"] = value.get('middle')
                extracted[f"{key}_lower"] = value.get('lower')
            else:
                # Regular indicator - keep as is
                extracted[key] = value

        return extracted

    async def initialize(self, min_connections=None, max_connections=None, command_timeout=None):
        """Initialize ultra-fast database with optimized settings"""
        logger.debug(f"ultra_fast_db.initialize() called, current initialized flag: {self.initialized}")

        if self.initialized:
            logger.debug("Already initialized, returning True")
            return True

        async with self._init_lock:
            if self.initialized:
                logger.debug("Already initialized (after lock), returning True")
                return True

            try:
                logger.debug("Starting initialization process...")
                # Create database if not exists
                await self._create_database_if_not_exists()

                # Override pool config if provided (for ultra-fast cron)
                pool_config = self.pool_config.copy()
                if min_connections:
                    pool_config['min_size'] = min_connections
                if max_connections:
                    pool_config['max_size'] = max_connections
                if command_timeout:
                    pool_config['command_timeout'] = command_timeout

                # Create optimized connection pool
                self.pool = await asyncpg.create_pool(
                    **self.db_config,
                    **pool_config,
                    setup=self._setup_connection,
                    server_settings={
                        'application_name': 'ultra_fast_stocks_service',
                        'jit': 'off'
                    }
                )

                # Create unified table structure
                await self._create_unified_tables()

                # IMPORTANT: Do NOT apply migrations during normal initialization
                # Migrations should ONLY be applied during hard-refresh
                # This prevents unwanted table modifications when queries trigger indicator calculations
                # await self._check_and_apply_migrations()  # DISABLED - only run during hard refresh

                self.initialized = True
                logger.info(f"🚀 Ultra-fast database initialized with {self.max_connections} max connections")
                return True

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
                    day_of_week INTEGER,                         -- Day within week (1=Mon, 5=Fri)
                    weekly_candle_key_id VARCHAR(50),            -- Foreign key to weekly_candles
                    monthly_candle_key_id VARCHAR(50),           -- Foreign key to monthly_candles
                    -- Weekly OHLCV columns (dynamic sliding window)
                    weekly_open DECIMAL(20,6),                   -- Weekly opening price (first day of week)
                    weekly_high DECIMAL(20,6),                   -- Weekly high (max from week start to current day)
                    weekly_low DECIMAL(20,6),                    -- Weekly low (min from week start to current day)
                    weekly_close DECIMAL(20,6),                  -- Weekly close (current day close)
                    weekly_volume BIGINT,                        -- Weekly volume (sum from week start to current day)
                    -- Monthly OHLCV columns (dynamic sliding window)
                    monthly_open DECIMAL(20,6),                  -- Monthly opening price (first day of month)
                    monthly_high DECIMAL(20,6),                  -- Monthly high (max from month start to current day)
                    monthly_low DECIMAL(20,6),                   -- Monthly low (min from month start to current day)
                    monthly_close DECIMAL(20,6),                 -- Monthly close (current day close)
                    monthly_volume BIGINT,                       -- Monthly volume (sum from month start to current day)
                    indicators JSONB DEFAULT '{}',               -- All indicators in JSONB
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create weekly candles table with optimized structure for O(1) lookups
            await conn.execute("""
                CREATE TABLE weekly_candles (
                    weekly_candle_key_id    VARCHAR(50) PRIMARY KEY,    -- "20MICRONS_W1", "20MICRONS_W2"
                    symbol                  VARCHAR(50) NOT NULL,       -- "20MICRONS"
                    week_sequence_number    INTEGER NOT NULL,           -- 1, 2, 3...
                    week_start_timestamp    BIGINT NOT NULL,            -- Monday timestamp
                    week_end_timestamp      BIGINT NOT NULL,            -- Friday timestamp  
                    week_start_datetime     TIMESTAMP NOT NULL,         -- Monday datetime
                    week_end_datetime       TIMESTAMP NOT NULL,         -- Friday datetime
                    open                    NUMERIC NOT NULL,           -- Monday open
                    high                    NUMERIC NOT NULL,           -- Week max high
                    low                     NUMERIC NOT NULL,           -- Week min low
                    close                   NUMERIC NOT NULL,           -- Friday close
                    volume                  BIGINT NOT NULL,            -- Week total volume
                    trading_days_count      INTEGER NOT NULL,           -- Days in week (1-5)
                    monthly_candle_key_id   VARCHAR(50),                -- Foreign key to monthly_candles
                    indicators              JSONB DEFAULT '{}',         -- Weekly indicators
                    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, week_sequence_number)
                )
            """)
            
            # Create monthly candles table with consistent structure (JSONB indicators like daily/weekly)
            await conn.execute("""
                CREATE TABLE monthly_candles (
                    monthly_candle_key_id VARCHAR(50) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    month_sequence_number INTEGER NOT NULL,
                    month_start_timestamp BIGINT NOT NULL,
                    month_end_timestamp BIGINT NOT NULL,
                    month_start_datetime TIMESTAMP NOT NULL,
                    month_end_datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    trading_days_count INTEGER NOT NULL DEFAULT 20,
                    indicators JSONB,
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
                    latest_monthly_key INTEGER DEFAULT -1,       -- Monthly key tracking
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
                        latest_monthly_key INTEGER DEFAULT -1,       -- Monthly key tracking
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
            
            # Monthly candles table to match TimeframeAggregator expectations
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_candles (
                    symbol VARCHAR(20) NOT NULL,
                    month_start_timestamp BIGINT NOT NULL,
                    month_start_date DATE NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    trading_days INTEGER DEFAULT 20,
                    indicators JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, month_start_timestamp)
                )
            """)
            
            # Create performance indexes
            await self._create_performance_indexes(conn)
            
            # Run OHLCV columns migration for existing tables
            await self._migrate_add_ohlcv_columns(conn)
            
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
        logger.info("Creating performance indexes...")
        
        # Create indexes for each table individually
        tables = [
            ('daily', 'daily_candles'),
            ('weekly', 'weekly_candles'), 
            ('monthly', 'monthly_candles')
        ]
        
        for timeframe, table_name in tables:
            try:
                # Check if this specific table exists
                table_exists = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = '{table_name}'
                    )
                """)
                
                if not table_exists:
                    logger.info(f"Table {table_name} doesn't exist, skipping indexes")
                    continue
                
                # Find the appropriate sequence column for each table
                sequence_column = None
                possible_sequence_columns = ['candle_sequence_number', 'week_sequence_number', 'month_sequence_number']
                
                # Monthly candles table has a different structure, skip sequence for it
                if table_name == 'monthly_candles':
                    sequence_column = None
                    logger.info(f"No sequence column for {table_name} (uses composite primary key)")
                else:
                    for col in possible_sequence_columns:
                        has_sequence_column = await conn.fetchval(f"""
                            SELECT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = '{table_name}' AND column_name = '{col}'
                            )
                        """)
                        if has_sequence_column:
                            sequence_column = col
                            break
                
                # Create sequence-based index if available
                if sequence_column:
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_sequence 
                        ON {table_name}(symbol, {sequence_column} DESC)
                    """)
                    logger.info(f"Created symbol+sequence index for {table_name} using {sequence_column}")
                else:
                    logger.info(f"No sequence column found for {table_name}, will use timestamp-based indexes only")
                
                # Find the appropriate timestamp column for each table
                timestamp_column = None
                if table_name == 'monthly_candles':
                    possible_timestamp_columns = ['month_start_timestamp']
                else:
                    possible_timestamp_columns = ['timestamp', 'week_start_timestamp', 'month_start_timestamp']
                
                for col in possible_timestamp_columns:
                    has_timestamp_column = await conn.fetchval(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = '{table_name}' AND column_name = '{col}'
                        )
                    """)
                    if has_timestamp_column:
                        timestamp_column = col
                        break
                
                if timestamp_column:
                    # Create timestamp index
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{timeframe}_timestamp 
                        ON {table_name}({timestamp_column} DESC)
                    """)
                    logger.info(f"Created timestamp index for {table_name} using {timestamp_column}")
                    
                    # Create symbol+timestamp index (alternative to sequence index)
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_timestamp 
                        ON {table_name}(symbol, {timestamp_column} DESC)
                    """)
                    logger.info(f"Created symbol+timestamp index for {table_name} using {timestamp_column}")
                else:
                    logger.warning(f"No timestamp column found for {table_name}, skipping timestamp indexes")
                
                # Create indicators GIN index if column exists
                has_indicators = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = '{table_name}' AND column_name = 'indicators'
                    )
                """)
                
                if has_indicators:
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{timeframe}_indicators 
                        ON {table_name} USING GIN (indicators)
                    """)
                    logger.info(f"Created indicators GIN index for {table_name}")
                
                # Create monthly_candle_key_id indexes for daily and weekly candles
                if timeframe in ['daily', 'weekly']:
                    has_monthly_candle_key_id = await conn.fetchval(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = '{table_name}' AND column_name = 'monthly_candle_key_id'
                        )
                    """)
                    
                    if has_monthly_candle_key_id:
                        await conn.execute(f"""
                            CREATE INDEX IF NOT EXISTS idx_{timeframe}_monthly_key_id 
                            ON {table_name}(monthly_candle_key_id)
                        """)
                        
                        logger.info(f"Created monthly_candle_key_id index for {table_name}")
                
            except Exception as e:
                logger.error(f"Failed to create indexes for {table_name}: {e}")
                # Continue with other tables instead of failing completely
        
        logger.info("Performance indexes creation completed")

    async def get_next_key_batch(self, symbol: str, batch_size: int, timeframe: str = 'daily') -> int:
        """Get the next batch of keys for a symbol (thread-safe)"""
        async with self.pool.acquire() as conn:
            # Use the new symbol_latest_keys table
            timeframe_key_col = f'latest_{timeframe}_key'
            timeframe_count_col = f'total_{timeframe}_candles'
            
            # Atomic increment to get next key batch
            # When inserting new row, start from batch_size - 1 (so first key is 0)
            # When updating, add batch_size to existing value
            result = await conn.fetchrow(f"""
                INSERT INTO symbol_latest_keys (symbol, {timeframe_key_col}, {timeframe_count_col})
                VALUES ($1, $2 - 1, $2)
                ON CONFLICT (symbol)
                DO UPDATE SET
                    {timeframe_key_col} = symbol_latest_keys.{timeframe_key_col} + $2,
                    {timeframe_count_col} = symbol_latest_keys.{timeframe_count_col} + $2,
                    last_updated = CURRENT_TIMESTAMP
                RETURNING
                    CASE
                        WHEN symbol_latest_keys.{timeframe_key_col} IS NULL OR symbol_latest_keys.{timeframe_key_col} = -1
                        THEN 0
                        ELSE symbol_latest_keys.{timeframe_key_col} - $2 + 1
                    END as start_key
            """, symbol, batch_size)
            
            return result['start_key']

    async def update_latest_candle(self, symbol: str, candle_data: Dict,
                                 timeframe: str = 'daily') -> bool:
        """
        Update or insert today's latest candle for a symbol.
        This is specifically for latest candle updates, not bulk data loading.

        Args:
            symbol: Stock symbol
            candle_data: Single candle data dict
            timeframe: Timeframe (daily, weekly, monthly)

        Returns:
            True if successful, False otherwise
        """
        if not candle_data or not isinstance(candle_data, dict):
            return False

        try:
            # Filter and validate OHLCV data
            enhanced_data = self._filter_valid_ohlcv_data([candle_data], symbol)
            if not enhanced_data:
                logger.warning(f"No valid OHLCV data for latest candle update: {symbol}")
                return False

            candle = enhanced_data[0]
            candle_timestamp = candle.get('timestamp', 0)
            candle_datetime = datetime.fromtimestamp(candle_timestamp / 1000)
            today_date = candle_datetime.date()

            async with self.pool.acquire() as conn:
                # Check if today's candle already exists for this symbol
                existing_candle = await conn.fetchrow("""
                    SELECT candle_key_id, candle_sequence_number
                    FROM daily_candles
                    WHERE symbol = $1 AND DATE(datetime) = $2
                    ORDER BY candle_sequence_number DESC
                    LIMIT 1
                """, symbol, today_date)

                if existing_candle:
                    # Today's candle exists - UPDATE it
                    candle_key_id = existing_candle['candle_key_id']
                    sequence_number = existing_candle['candle_sequence_number']

                    logger.debug(f"🔄 Updating existing candle for {symbol} on {today_date} (key: {candle_key_id})")

                    await conn.execute("""
                        UPDATE daily_candles SET
                            timestamp = $1,
                            datetime = $2,
                            open = $3,
                            high = $4,
                            low = $5,
                            close = $6,
                            volume = $7,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = $8
                    """,
                    candle_timestamp,
                    candle_datetime,
                    float(candle.get('open', 0)),
                    float(candle.get('high', 0)),
                    float(candle.get('low', 0)),
                    float(candle.get('close', 0)),
                    int(candle.get('volume', 0)),
                    candle_key_id
                    )

                    logger.debug(f"✅ Updated existing candle for {symbol}: {candle_key_id}")

                else:
                    # Today's candle doesn't exist - CREATE it
                    start_key = await self.get_next_key_batch(symbol, 1, timeframe)
                    sequence_number = start_key
                    candle_key_id = f"{symbol}_{sequence_number}"

                    logger.debug(f"🆕 Creating new candle for {symbol} on {today_date} (key: {candle_key_id})")

                    # Calculate day of week and assign monthly candle key
                    day_of_week = (sequence_number % 5) + 1

                    # Find monthly assignment
                    monthly_assignments = await self._find_monthly_assignments_for_daily_candles_bulk(
                        conn, [(symbol, candle_datetime)]
                    )
                    _, monthly_candle_key_id = monthly_assignments.get(
                        (symbol, candle_datetime), (None, None)
                    )

                    await conn.execute("""
                        INSERT INTO daily_candles
                        (candle_key_id, symbol, candle_sequence_number, timestamp, datetime,
                         open, high, low, close, volume, day_of_week, weekly_candle_key_id,
                         indicators, monthly_candle_key_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    candle_key_id,
                    symbol,
                    sequence_number,
                    candle_timestamp,
                    candle_datetime,
                    float(candle.get('open', 0)),
                    float(candle.get('high', 0)),
                    float(candle.get('low', 0)),
                    float(candle.get('close', 0)),
                    int(candle.get('volume', 0)),
                    day_of_week,
                    None,  # weekly_candle_key_id
                    '{}',  # empty indicators
                    monthly_candle_key_id
                    )

                    logger.debug(f"✅ Created new candle for {symbol}: {candle_key_id}")

                # Calculate OHLCV for the updated/inserted data
                await self._calculate_ohlcv_for_symbol(symbol)

                return True

        except Exception as e:
            logger.error(f"❌ Failed to update latest candle for {symbol}: {e}")
            return False

    async def bulk_update_latest_candles(self, candles_batch: List[Tuple[str, Dict]],
                                        timeframe: str = 'daily') -> Dict[str, bool]:
        """
        Bulk update latest candles for multiple symbols in a single database transaction.
        Optimized for cron job performance with batch processing.

        Args:
            candles_batch: List of (symbol, candle_data) tuples
            timeframe: Timeframe (daily, weekly, monthly)

        Returns:
            Dict mapping symbol to success status
        """
        if not candles_batch:
            return {}

        results = {}

        try:
            async with self.pool.acquire() as conn:
                # Start a transaction for atomic batch processing
                async with conn.transaction():
                    # Prepare batch data
                    updates = []
                    inserts = []

                    for symbol, candle_data in candles_batch:
                        if not candle_data or not isinstance(candle_data, dict):
                            results[symbol] = False
                            continue

                        # Filter and validate OHLCV data
                        enhanced_data = self._filter_valid_ohlcv_data([candle_data], symbol)
                        if not enhanced_data:
                            logger.warning(f"No valid OHLCV data for {symbol}")
                            results[symbol] = False
                            continue

                        candle = enhanced_data[0]
                        candle_timestamp = candle.get('timestamp', 0)
                        candle_datetime = datetime.fromtimestamp(candle_timestamp / 1000)
                        today_date = candle_datetime.date()

                        # Check if today's candle exists (batch check)
                        existing_candle = await conn.fetchrow("""
                            SELECT candle_key_id, candle_sequence_number
                            FROM daily_candles
                            WHERE symbol = $1 AND DATE(datetime) = $2
                            ORDER BY candle_sequence_number DESC
                            LIMIT 1
                        """, symbol, today_date)

                        if existing_candle:
                            # Prepare UPDATE
                            updates.append((
                                candle_timestamp,
                                candle_datetime,
                                float(candle.get('open', 0)),
                                float(candle.get('high', 0)),
                                float(candle.get('low', 0)),
                                float(candle.get('close', 0)),
                                int(candle.get('volume', 0)),
                                existing_candle['candle_key_id']
                            ))
                        else:
                            # Prepare INSERT
                            start_key = await self.get_next_key_batch(symbol, 1, timeframe)
                            sequence_number = start_key
                            candle_key_id = f"{symbol}_{sequence_number}"
                            day_of_week = (sequence_number % 5) + 1

                            # Find monthly assignment
                            monthly_assignments = await self._find_monthly_assignments_for_daily_candles_bulk(
                                conn, [(symbol, candle_datetime)]
                            )
                            _, monthly_candle_key_id = monthly_assignments.get(
                                (symbol, candle_datetime), (None, None)
                            )

                            inserts.append((
                                candle_key_id,
                                symbol,
                                sequence_number,
                                candle_timestamp,
                                candle_datetime,
                                float(candle.get('open', 0)),
                                float(candle.get('high', 0)),
                                float(candle.get('low', 0)),
                                float(candle.get('close', 0)),
                                int(candle.get('volume', 0)),
                                day_of_week,
                                None,  # weekly_candle_key_id
                                '{}',  # empty indicators
                                monthly_candle_key_id
                            ))

                    # Execute bulk UPDATE
                    if updates:
                        await conn.executemany("""
                            UPDATE daily_candles SET
                                timestamp = $1,
                                datetime = $2,
                                open = $3,
                                high = $4,
                                low = $5,
                                close = $6,
                                volume = $7,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE candle_key_id = $8
                        """, updates)
                        logger.info(f"✅ Bulk updated {len(updates)} existing candles")

                    # Execute bulk INSERT
                    if inserts:
                        await conn.executemany("""
                            INSERT INTO daily_candles
                            (candle_key_id, symbol, candle_sequence_number, timestamp, datetime,
                             open, high, low, close, volume, day_of_week, weekly_candle_key_id,
                             indicators, monthly_candle_key_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                        """, inserts)
                        logger.info(f"✅ Bulk inserted {len(inserts)} new candles")

                    # Mark all as successful
                    for symbol, _ in candles_batch:
                        if symbol not in results:
                            results[symbol] = True

                    # Calculate OHLCV for all updated symbols in batch
                    unique_symbols = list(set([symbol for symbol, _ in candles_batch]))
                    for symbol in unique_symbols:
                        await self._calculate_ohlcv_for_symbol(symbol)

            return results

        except Exception as e:
            logger.error(f"❌ Failed bulk update of latest candles: {e}")
            # Mark all as failed on error
            return {symbol: False for symbol, _ in candles_batch}

    async def store_chunk_with_indicators(self, symbol: str, chunk_data: List[Dict],
                                        timeframe: str = 'daily') -> bool:
        """
        Store a chunk of processed data with indicators using new composite key structure.
        This enables streaming processing without waiting for entire stock completion.
        """
        if not chunk_data:
            return True
        
        try:
            # Filter and validate OHLCV data only - NO CALCULATIONS
            enhanced_chunk_data = self._filter_valid_ohlcv_data(chunk_data, symbol)
            
            # Get next key batch for this chunk
            start_key = await self.get_next_key_batch(symbol, len(enhanced_chunk_data), timeframe)
            
            # Prepare data with composite keys using new structure
            values = []
            for i, candle in enumerate(enhanced_chunk_data):
                sequence_number = start_key + i
                candle_key_id = f"{symbol}_{sequence_number}"  # New composite primary key
                
                # Handle both dict and string data formats
                if isinstance(candle, str):
                    logger.warning(f"Skipping string data for {symbol}: {candle}")
                    continue
                elif not isinstance(candle, dict):
                    logger.warning(f"Skipping invalid data type for {symbol}: {type(candle)}")
                    continue
                
                # Calculate daily data within week
                day_of_week = (sequence_number % 5) + 1  # Day within week (1=Mon, 5=Fri)
                weekly_candle_key_id = None  # Will be populated later during weekly candle generation
                
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
                    int(candle.get('volume', 0)),           # volume
                    day_of_week,                            # day_of_week
                    weekly_candle_key_id                    # weekly_candle_key_id (NULL initially)
                ]
                
                # No indicators - empty JSONB object (calculations done by PostgreSQL)
                ohlcv_data.append('{}')  # Empty indicators JSONB - will be populated by stored procedures
                values.append(tuple(ohlcv_data))
            
            # Bulk insert chunk using new table structure
            table_name = f"{timeframe}_candles"
            async with self.pool.acquire() as conn:
                # If this is daily candles, find monthly assignments
                if timeframe == 'daily':
                    # Filter out non-dict objects before processing timestamps
                    valid_candles = [candle for candle in enhanced_chunk_data 
                                   if isinstance(candle, dict)]
                    monthly_assignments = await self._find_monthly_assignments_for_daily_candles_bulk(
                        conn, [(symbol, datetime.fromtimestamp(candle.get('timestamp', 0) / 1000)) 
                               for candle in valid_candles]
                    )
                    
                    # Add monthly_candle_key_id to values
                    valid_candle_index = 0
                    for i, candle in enumerate(enhanced_chunk_data):
                        if isinstance(candle, dict):
                            candle_datetime = datetime.fromtimestamp(candle.get('timestamp', 0) / 1000)
                            _, monthly_candle_key_id = monthly_assignments.get(
                                (symbol, candle_datetime), (None, None)
                            )
                            # Extend the row data for this candle with monthly field
                            if valid_candle_index < len(values):
                                values[valid_candle_index] = values[valid_candle_index] + (monthly_candle_key_id,)
                                valid_candle_index += 1
                    
                    await conn.executemany(f"""
                        INSERT INTO {table_name} 
                        (candle_key_id, symbol, candle_sequence_number, timestamp, datetime, 
                         open, high, low, close, volume, day_of_week, weekly_candle_key_id, indicators,
                         monthly_candle_key_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                        ON CONFLICT (candle_key_id) 
                        DO UPDATE SET
                            timestamp = EXCLUDED.timestamp,
                            datetime = EXCLUDED.datetime,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            day_of_week = EXCLUDED.day_of_week,
                            weekly_candle_key_id = EXCLUDED.weekly_candle_key_id,
                            indicators = EXCLUDED.indicators,
                            monthly_candle_key_id = EXCLUDED.monthly_candle_key_id,
                            updated_at = CURRENT_TIMESTAMP
                    """, values)
                else:
                    # For non-daily candles (if any), use the original INSERT without monthly fields
                    await conn.executemany(f"""
                        INSERT INTO {table_name} 
                        (candle_key_id, symbol, candle_sequence_number, timestamp, datetime, 
                         open, high, low, close, volume, day_of_week, weekly_candle_key_id, indicators)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        ON CONFLICT (candle_key_id) 
                        DO UPDATE SET
                            timestamp = EXCLUDED.timestamp,
                            datetime = EXCLUDED.datetime,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            day_of_week = EXCLUDED.day_of_week,
                            weekly_candle_key_id = EXCLUDED.weekly_candle_key_id,
                            indicators = EXCLUDED.indicators,
                            updated_at = CURRENT_TIMESTAMP
                    """, values)
            
            logger.debug(f"✅ Stored chunk of {len(chunk_data)} candles for {symbol} (keys {start_key}-{start_key + len(chunk_data) - 1})")
            
            # Calculate OHLCV for the inserted data
            await self._calculate_ohlcv_for_symbol(symbol)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store chunk for {symbol}: {e}")
            return False

    async def _find_monthly_assignments_for_daily_candles_bulk(self, conn, candle_refs: List[Tuple[str, datetime]]) -> Dict[Tuple[str, datetime], Tuple[int, str]]:
        """Find monthly_candle_key_id for daily candles based on their date"""
        assignments = {}
        
        # Get unique symbols from candle references
        symbols = list(set(ref[0] for ref in candle_refs))
        
        # Get all monthly candles for these symbols
        monthly_candles = await conn.fetch("""
            SELECT symbol, month_sequence_number, monthly_candle_key_id,
                   month_start_datetime, month_end_datetime
            FROM monthly_candles 
            WHERE symbol = ANY($1)
            ORDER BY month_start_datetime
        """, symbols)
        
        # For each daily candle, find which monthly candle it belongs to
        for symbol, candle_datetime in candle_refs:
            candle_date = candle_datetime.date()
            
            # Find matching monthly candle
            monthly_candle_key_id = None
            
            for mc in monthly_candles:
                if (mc['symbol'] == symbol and 
                    mc['month_start_datetime'].date() <= candle_date <= mc['month_end_datetime'].date()):
                    monthly_candle_key_id = mc['monthly_candle_key_id']
                    break
            
            # Keep the same return format for compatibility, but monthly_key is always None now
            assignments[(symbol, candle_datetime)] = (None, monthly_candle_key_id)
        
        return assignments

    async def _assign_monthly_keys_to_weekly_candles(self, conn, symbol: str) -> None:
        """Assign monthly_candle_key_id to weekly candles based on their END dates (per user requirement)"""
        # Get all weekly candles for this symbol that don't have monthly_candle_key_id assigned
        weekly_candles = await conn.fetch("""
            SELECT weekly_candle_key_id, symbol, week_end_datetime 
            FROM weekly_candles 
            WHERE symbol = $1 AND monthly_candle_key_id IS NULL
            ORDER BY week_end_datetime
        """, symbol)
        
        if not weekly_candles:
            return
        
        # Get all monthly candles for this symbol
        monthly_candles = await conn.fetch("""
            SELECT symbol, month_sequence_number, monthly_candle_key_id,
                   month_start_datetime, month_end_datetime
            FROM monthly_candles 
            WHERE symbol = $1
            ORDER BY month_start_datetime
        """, symbol)
        
        # For each weekly candle, find which monthly candle it belongs to (based on END date per user requirement)
        updates_made = 0
        for weekly in weekly_candles:
            week_end_date = weekly['week_end_datetime'].date()
            
            # Find matching monthly candle
            monthly_candle_key_id = None
            
            for mc in monthly_candles:
                if (mc['symbol'] == symbol and 
                    mc['month_start_datetime'].date() <= week_end_date <= mc['month_end_datetime'].date()):
                    monthly_candle_key_id = mc['monthly_candle_key_id']
                    break
            
            # Update the weekly candle with monthly assignment
            if monthly_candle_key_id is not None:
                await conn.execute("""
                    UPDATE weekly_candles 
                    SET monthly_candle_key_id = $1
                    WHERE weekly_candle_key_id = $2
                """, monthly_candle_key_id, weekly['weekly_candle_key_id'])
                updates_made += 1
        
        if updates_made > 0:
            logger.debug(f"SUCCESS: Assigned monthly_candle_key_id to {updates_made} weekly candles for {symbol}")

    async def _assign_monthly_keys_to_daily_candles(self, conn, symbol: str) -> None:
        """Assign monthly_candle_key_id to daily candles based on their date"""
        # Get all daily candles for this symbol that don't have monthly_candle_key_id assigned
        daily_candles = await conn.fetch("""
            SELECT candle_key_id, symbol, datetime 
            FROM daily_candles 
            WHERE symbol = $1 AND monthly_candle_key_id IS NULL
            ORDER BY datetime
        """, symbol)
        
        if not daily_candles:
            return
        
        # Get all monthly candles for this symbol
        monthly_candles = await conn.fetch("""
            SELECT symbol, month_sequence_number, monthly_candle_key_id,
                   month_start_datetime, month_end_datetime
            FROM monthly_candles 
            WHERE symbol = $1
            ORDER BY month_start_datetime
        """, symbol)
        
        # For each daily candle, find which monthly candle it belongs to (based on date)
        updates_made = 0
        for daily in daily_candles:
            daily_date = daily['datetime'].date()
            
            # Find matching monthly candle
            monthly_candle_key_id = None
            
            for mc in monthly_candles:
                if (mc['symbol'] == symbol and 
                    mc['month_start_datetime'].date() <= daily_date <= mc['month_end_datetime'].date()):
                    monthly_candle_key_id = mc['monthly_candle_key_id']
                    break
            
            # Update the daily candle with monthly assignment
            if monthly_candle_key_id is not None:
                await conn.execute("""
                    UPDATE daily_candles 
                    SET monthly_candle_key_id = $1
                    WHERE candle_key_id = $2
                """, monthly_candle_key_id, daily['candle_key_id'])
                updates_made += 1
        
        if updates_made > 0:
            logger.debug(f"SUCCESS: Assigned monthly_candle_key_id to {updates_made} daily candles for {symbol}")

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
                        # Extract Bollinger Bands fields
                        indicators = self._extract_bollinger_bands_fields(indicators)
                        result.update(indicators)
                    return result
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get candle {symbol}_{key_number}: {e}")
            return None

    async def get_last_n_candles(self, symbol: str, n: int, 
                                timeframe: str = 'daily') -> List[Dict]:
        """Get last N candles for a symbol (works with available data only)"""
        try:
            table_name = f"{timeframe}_candles"
            
            async with self.pool.acquire() as conn:
                # Get available candles for this symbol, ordered by timestamp/sequence
                # Use whichever ordering column is available
                has_sequence_column = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = '{table_name}' AND column_name = 'candle_sequence_number'
                    )
                """)
                
                if has_sequence_column:
                    order_by = "candle_sequence_number DESC"
                else:
                    order_by = "timestamp DESC"
                
                # Get last N available candles (or all if less than N)
                rows = await conn.fetch(f"""
                    SELECT * FROM {table_name} 
                    WHERE symbol = $1 
                    ORDER BY {order_by}
                    LIMIT $2
                """, symbol, n)
                
                if not rows:
                    logger.info(f"No candles found for symbol {symbol} in {table_name}")
                    return []
                
                # Reverse to get chronological order (oldest first)
                rows = list(reversed(rows))
                
                results = []
                for row in rows:
                    result = dict(row)
                    # Parse indicators from JSONB
                    if result.get('indicators'):
                        indicators = json.loads(result['indicators']) if isinstance(result['indicators'], str) else result['indicators']
                        # Extract Bollinger Bands fields
                        indicators = self._extract_bollinger_bands_fields(indicators)
                        result.update(indicators)
                    results.append(result)
                
                logger.info(f"Retrieved {len(results)} candles for {symbol} (requested {n})")
                return results
                
        except Exception as e:
            logger.error(f"Failed to get last {n} candles for {symbol}: {e}")
            return []

    async def get_candles_with_indicators(self, symbol: str, limit: Optional[int] = None,
                                         timeframe: str = 'daily') -> List[Dict]:
        """Get candles with indicators for query processing (all candles if limit is None)"""
        try:
            table_name = f"{timeframe}_candles"
            
            async with self.pool.acquire() as conn:
                # Check which ordering column is available
                has_sequence_column = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = '{table_name}' AND column_name = 'candle_sequence_number'
                    )
                """)
                
                if has_sequence_column:
                    order_by = "candle_sequence_number DESC"
                else:
                    order_by = "timestamp DESC"
                
                # Build query with optional limit
                if limit:
                    query = f"""
                        SELECT * FROM {table_name} 
                        WHERE symbol = $1 
                        ORDER BY {order_by}
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, symbol, limit)
                else:
                    query = f"""
                        SELECT * FROM {table_name} 
                        WHERE symbol = $1 
                        ORDER BY {order_by}
                    """
                    rows = await conn.fetch(query, symbol)
                
                if not rows:
                    return []
                
                # Reverse to get chronological order (oldest first) for query processing
                rows = list(reversed(rows))
                
                results = []
                for row in rows:
                    result = dict(row)
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get candles with indicators for {symbol}: {e}")
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
        Example: [{'name': 'indicator_name', 'operator': '>', 'value': 70}]
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
                        # Extract Bollinger Bands fields
                        indicators = self._extract_bollinger_bands_fields(indicators)
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

    async def update_indicator_in_jsonb(self, symbol: str, indicator_key: str, indicator_values: List[Dict]) -> bool:
        """
        Update a specific indicator in the JSONB column for a symbol.
        
        Args:
            symbol: Stock symbol
            indicator_key: Key for the indicator (e.g., 'supertrend_10_1dot2', 'daily_pctchg_1')
            indicator_values: List of dicts with timestamp and indicator value
            
        Returns:
            True if successful
        """
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                # Update indicators in JSONB for each candle (including null values)
                updated_count = 0
                for value_dict in indicator_values:
                    timestamp = value_dict.get('timestamp')
                    value = value_dict.get('value')
                    
                    # Process all values including null (timestamp must exist though)
                    if timestamp is not None:
                        if value is not None:
                            # Convert value to float if it's a Decimal or other numeric type
                            if hasattr(value, '__float__'):
                                value = float(value)
                            
                            # Round to 2 decimal places for precision control
                            if isinstance(value, (int, float)):
                                value = round(float(value), 2)
                            
                            # Update JSONB with numeric value
                            result = await conn.execute("""
                                UPDATE daily_candles
                                SET indicators = jsonb_set(
                                    COALESCE(indicators, '{}'),
                                    $1::text[],
                                    to_jsonb($2::numeric)
                                )
                                WHERE symbol = $3 AND timestamp = $4
                            """, [indicator_key], value, symbol, timestamp)
                        else:
                            # Store null value in JSONB for insufficient data cases
                            result = await conn.execute("""
                                UPDATE daily_candles
                                SET indicators = jsonb_set(
                                    COALESCE(indicators, '{}'),
                                    $1::text[],
                                    'null'::jsonb
                                )
                                WHERE symbol = $2 AND timestamp = $3
                            """, [indicator_key], symbol, timestamp)
                        
                        # Check if any rows were updated
                        if result.split()[-1] != '0':  # Result format: "UPDATE n"
                            updated_count += 1
                
                logger.info(f"Updated {indicator_key} for {symbol} - {updated_count}/{len(indicator_values)} values updated")
                return updated_count > 0
                
        except Exception as e:
            logger.error(f"Error updating indicator {indicator_key} for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _filter_valid_ohlcv_data(self, chunk_data: List[Dict], symbol: str) -> List[Dict]:
        """
        Filter and clean OHLCV data for database insertion.
        NO CALCULATIONS - Only data cleaning and validation.
        All indicators will be calculated by PostgreSQL stored procedures.
        """
        if not chunk_data or len(chunk_data) == 0:
            return chunk_data
            
        logger.debug(f"Filtering OHLCV data for {len(chunk_data)} candles of {symbol}")
        
        # Filter out invalid data to get clean candle list
        valid_candles = []
        for candle in chunk_data:
            if isinstance(candle, str):
                logger.warning(f"Skipping string data for {symbol}: {candle}")
                continue
            elif not isinstance(candle, dict):
                logger.warning(f"Skipping invalid data type for {symbol}: {type(candle)}")
                continue
            
            # Validate required OHLCV fields
            required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if all(field in candle for field in required_fields):
                valid_candles.append(candle)
            else:
                logger.warning(f"Skipping candle with missing OHLCV fields for {symbol}")
                continue
        
        if not valid_candles:
            logger.warning(f"No valid OHLCV data found for {symbol}")
            return chunk_data
            
        logger.debug(f"Filtered {len(valid_candles)} valid OHLCV candles for {symbol}")
        return valid_candles
    
    # REMOVED: All calculation methods moved to PostgreSQL stored procedures
    # Python server is now only responsible for OHLCV data ingestion

    async def call_database_calculations(self, symbol: str) -> Dict[str, Any]:
        """
        Call PostgreSQL stored procedures to perform all calculations.
        This ensures single source of truth in the database.
        
        Args:
            symbol: Stock symbol to process
            
        Returns:
            Dict with calculation results
        """
        try:
            start_time = time.time()
            logger.info(f"🔢 Calling database calculations for {symbol}")
            
            async with self.pool.acquire() as conn:
                # Call comprehensive PostgreSQL stored procedure
                result = await conn.fetchrow("""
                    SELECT * FROM process_symbol_comprehensive($1)
                """, symbol)
                
                processing_time = time.time() - start_time
                
                if result and result['status'] == 'SUCCESS':
                    logger.info(f"✅ Database calculation for {symbol}: "
                              f"{result['weekly_candles_generated']} weekly candles, "
                              f"{result['daily_candles_updated']} daily updated in {processing_time:.3f}s")
                    
                    return {
                        "success": True,
                        "symbol": symbol,
                        "weekly_candles_generated": result['weekly_candles_generated'],
                        "daily_candles_updated": result['daily_candles_updated'],
                        "indicators_calculated": result['indicators_calculated'],
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_comprehensive_procedure"
                    }
                else:
                    error_msg = result['status'] if result else "No result returned"
                    logger.error(f"❌ Database calculation failed for {symbol}: {error_msg}")
                    
                    return {
                        "success": False,
                        "symbol": symbol,
                        "error": error_msg,
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_comprehensive_procedure"
                    }
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Database calculation failed for {symbol}: {e}")
            
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "processing_time_seconds": round(processing_time, 3),
                "method": "postgresql_comprehensive_procedure"
            }

    async def call_database_weekly_only(self, symbol: str) -> Dict[str, Any]:
        """
        Call PostgreSQL stored procedures to generate ONLY weekly candles (no indicators).
        Used during hard refresh to avoid calculating indicators.
        
        Args:
            symbol: Stock symbol to process
            
        Returns:
            Dict with weekly generation results
        """
        try:
            start_time = time.time()
            logger.info(f"📅 Calling weekly-only processing for {symbol}")
            
            async with self.pool.acquire() as conn:
                # Call weekly-only PostgreSQL stored procedure
                result = await conn.fetchrow("""
                    SELECT * FROM process_symbol_weekly_only($1)
                """, symbol)
                
                processing_time = time.time() - start_time
                
                if result and result['status'] == 'SUCCESS':
                    logger.info(f"✅ Weekly-only processing for {symbol}: "
                              f"{result['weekly_candles_generated']} weekly candles, "
                              f"{result['daily_candles_updated']} daily updated in {processing_time:.3f}s")
                    
                    return {
                        "success": True,
                        "symbol": symbol,
                        "weekly_candles_generated": result['weekly_candles_generated'],
                        "daily_candles_updated": result['daily_candles_updated'],
                        "indicators_calculated": [],  # No indicators calculated
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_weekly_only_procedure"
                    }
                else:
                    error_msg = result['status'] if result else "No result returned"
                    logger.error(f"❌ Weekly-only processing failed for {symbol}: {error_msg}")
                    
                    return {
                        "success": False,
                        "symbol": symbol,
                        "error": error_msg,
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_weekly_only_procedure"
                    }
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Weekly-only processing failed for {symbol}: {e}")
            
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "processing_time_seconds": round(processing_time, 3),
                "method": "postgresql_weekly_only_procedure"
            }
    
    async def call_database_weekly_only_all_symbols(self) -> Dict[str, Any]:
        """
        Call PostgreSQL stored procedures to generate ONLY weekly candles for all symbols (no indicators).
        Used during hard refresh to avoid calculating indicators.
        
        Returns:
            Dict with batch processing results
        """
        try:
            start_time = time.time()
            logger.info("📅 Starting weekly-only processing for all symbols")
            
            async with self.pool.acquire() as conn:
                # Call batch weekly-only PostgreSQL stored procedure (returns multiple rows)
                results = await conn.fetch("""
                    SELECT * FROM process_all_symbols_weekly_only()
                """)
                
                processing_time = time.time() - start_time
                
                if results:
                    # Count successful and failed results
                    successful = sum(1 for r in results if r['status'] == 'SUCCESS')
                    failed = len(results) - successful
                    total_weekly_candles = sum(r['weekly_candles'] for r in results if r['status'] == 'SUCCESS')
                    total_daily_updated = sum(r['daily_updated'] for r in results if r['status'] == 'SUCCESS')
                    
                    logger.info(f"✅ Weekly-only batch processing completed: "
                              f"{successful}/{len(results)} symbols successful, "
                              f"{total_weekly_candles} weekly candles generated in {processing_time:.3f}s")
                    
                    return {
                        "success": True,
                        "successful": successful,
                        "failed": failed,
                        "total_symbols": len(results),
                        "total_weekly_candles": total_weekly_candles,
                        "total_daily_updated": total_daily_updated,
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_batch_weekly_only_procedure",
                        "details": [{"symbol": r['symbol'], "status": r['status'], "weekly_candles": r['weekly_candles']} for r in results]
                    }
                else:
                    logger.error("❌ Weekly-only batch processing returned no results")
                    
                    return {
                        "success": False,
                        "successful": 0,
                        "failed": 0,
                        "total_symbols": 0,
                        "error": "No results returned",
                        "processing_time_seconds": round(processing_time, 3),
                        "method": "postgresql_batch_weekly_only_procedure"
                    }
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Failed to call batch weekly-only processing: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "successful": 0,
                "failed": 0,
                "error": str(e),
                "processing_time_seconds": round(processing_time, 3),
                "method": "postgresql_batch_weekly_only_procedure"
            }

    async def generate_and_store_weekly_candles(self, symbol: str) -> bool:
        """
        Generate weekly candles using PostgreSQL stored procedure.
        Single source of truth - all calculations done in database.
        
        Args:
            symbol: Stock symbol to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"🗓️ Generating weekly candles for {symbol}")
            
            async with self.pool.acquire() as conn:
                # Call PostgreSQL stored procedure for weekly candle generation
                result = await conn.fetchrow("""
                    SELECT * FROM generate_weekly_candles_for_symbol($1)
                """, symbol)
                
                if result and result['status'] == 'SUCCESS':
                    logger.info(f"✅ Generated {result['generated_weeks']} weekly candles for {symbol}, "
                              f"updated {result['updated_daily_refs']} daily references")
                    
                    # Now assign monthly_candle_key_id to the newly generated weekly candles
                    await self._assign_monthly_keys_to_weekly_candles(conn, symbol)
                    
                    return True
                else:
                    error_msg = result['status'] if result else "No result returned"
                    logger.error(f"❌ Weekly candle generation failed for {symbol}: {error_msg}")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Failed to generate weekly candles for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def generate_monthly_candles_for_symbol(self, symbol: str) -> bool:
        """
        Generate monthly candles for a single symbol using timeframe aggregator
        
        Args:
            symbol: Stock symbol to process
        """
        try:
            from services.timeframe_aggregator import TimeframeAggregator
            
            # Initialize timeframe aggregator with our pool
            aggregator = TimeframeAggregator(self.pool)
            
            # Generate monthly candles for this symbol
            candles_generated = await aggregator.generate_monthly_candles(symbol)
            
            if candles_generated > 0:
                logger.info(f"✅ Generated {candles_generated} monthly candles for {symbol}")
                return True
            else:
                logger.warning(f"⚠️ No monthly candles generated for {symbol}")
                return True  # Not an error, just no data to aggregate
                
        except Exception as e:
            logger.error(f"❌ Failed to generate monthly candles for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def batch_generate_weekly_candles(self, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Generate weekly candles using PostgreSQL stored procedure for all symbols.
        Single source of truth - all calculations done in database.
        
        Args:
            symbols: List of symbols to process. If None, processes all symbols
            
        Returns:
            Dict with processing statistics
        """
        try:
            start_time = time.time()
            
            logger.info(f"🗓️ Calling database to process all symbols comprehensively")
            
            async with self.pool.acquire() as conn:
                # Call the batch processing stored procedure
                results = await conn.fetch("SELECT * FROM process_all_symbols_comprehensive()")
                
                successful = 0
                failed = 0
                total_weekly_candles = 0
                total_daily_updated = 0
                
                # Process results from stored procedure
                successful_symbols = []
                for result in results:
                    if result['status'] == 'SUCCESS':
                        successful += 1
                        total_weekly_candles += result['weekly_candles']
                        total_daily_updated += result['daily_updated']
                        successful_symbols.append(result['symbol'])
                        logger.info(f"✅ {result['symbol']}: {result['weekly_candles']} weekly, {result['daily_updated']} daily updated")
                    else:
                        failed += 1
                        logger.error(f"❌ {result['symbol']}: {result['status']}")
                
                # Assign monthly_candle_key_id to all successfully generated weekly candles
                if successful_symbols:
                    logger.info(f"Assigning monthly_candle_key_id to weekly candles for {len(successful_symbols)} symbols...")
                    for symbol in successful_symbols:
                        await self._assign_monthly_keys_to_weekly_candles(conn, symbol)
                
                processing_time = time.time() - start_time
                
                return {
                    "successful_symbols": successful,
                    "failed_symbols": failed,
                    "total_symbols_processed": successful + failed,
                    "total_weekly_candles": total_weekly_candles,
                    "total_daily_updated": total_daily_updated,
                    "processing_time_seconds": round(processing_time, 2)
                }
            
        except Exception as e:
            logger.error(f"❌ Batch weekly candle generation failed: {e}")
            return {
                "successful_symbols": 0,
                "failed_symbols": len(symbols) if symbols else 0,
                "error": str(e)
            }

    async def batch_generate_monthly_candles(self, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Generate monthly candles using timeframe aggregator for all symbols.
        
        Args:
            symbols: List of symbols to process. If None, processes all symbols
            
        Returns:
            Dict with processing statistics
        """
        try:
            import time
            start_time = time.time()
            
            # Get symbols to process
            if not symbols:
                async with self.pool.acquire() as conn:
                    symbol_rows = await conn.fetch("SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol")
                    symbols = [row['symbol'] for row in symbol_rows]
            
            if not symbols:
                return {"successful_symbols": 0, "failed_symbols": 0, "message": "No symbols to process"}
            
            logger.info(f"🗓️ Generating monthly candles for {len(symbols)} symbols")
            
            successful = 0
            failed = 0
            total_monthly_candles = 0
            
            # Process each symbol
            for symbol in symbols:
                try:
                    success = await self.generate_monthly_candles_for_symbol(symbol)
                    if success:
                        successful += 1
                        # Count how many monthly candles were generated
                        async with self.pool.acquire() as conn:
                            count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles WHERE symbol = $1", symbol)
                            total_monthly_candles += count
                    else:
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"❌ Monthly candle generation failed for {symbol}: {e}")
                    failed += 1
            
            processing_time = time.time() - start_time
            
            logger.info(f"✅ Monthly candle generation completed: {successful} successful, {failed} failed, {total_monthly_candles} total candles generated")
            
            return {
                "successful_symbols": successful,
                "failed_symbols": failed,
                "total_symbols_processed": successful + failed,
                "total_monthly_candles": total_monthly_candles,
                "processing_time_seconds": round(processing_time, 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Batch monthly candle generation failed: {e}")
            return {
                "successful_symbols": 0,
                "failed_symbols": len(symbols) if symbols else 0,
                "error": str(e)
            }

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        async with self.pool.acquire() as conn:
            yield conn

    async def _migrate_add_ohlcv_columns(self, conn):
        """Add OHLCV columns to daily_candles table if they don't exist"""
        try:
            logger.info("🔄 Checking for OHLCV column migration...")
            
            # Check if weekly_open column exists
            column_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'daily_candles' 
                    AND column_name = 'weekly_open'
                )
            """)
            
            if column_exists:
                logger.info("✅ OHLCV columns already exist")
                return
                
            logger.info("🔧 Adding OHLCV columns to daily_candles table...")
            
            # Read and execute the migration SQL
            migration_sql = """
            -- Add weekly OHLCV columns
            ALTER TABLE daily_candles 
            ADD COLUMN IF NOT EXISTS weekly_open DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS weekly_high DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS weekly_low DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS weekly_close DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS weekly_volume BIGINT DEFAULT NULL;

            -- Add monthly OHLCV columns  
            ALTER TABLE daily_candles 
            ADD COLUMN IF NOT EXISTS monthly_open DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS monthly_high DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS monthly_low DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS monthly_close DECIMAL(20,6) DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS monthly_volume BIGINT DEFAULT NULL;

            -- Create indexes for better query performance
            CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_high ON daily_candles(weekly_high) WHERE weekly_high IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_low ON daily_candles(weekly_low) WHERE weekly_low IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_daily_candles_weekly_volume ON daily_candles(weekly_volume) WHERE weekly_volume IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_high ON daily_candles(monthly_high) WHERE monthly_high IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_low ON daily_candles(monthly_low) WHERE monthly_low IS NOT NULL;  
            CREATE INDEX IF NOT EXISTS idx_daily_candles_monthly_volume ON daily_candles(monthly_volume) WHERE monthly_volume IS NOT NULL;
            """
            
            await conn.execute(migration_sql)
            logger.info("✅ OHLCV columns migration completed successfully")
            
        except Exception as e:
            logger.error(f"❌ OHLCV columns migration failed: {e}")
            # Don't raise - allow system to continue

    async def _calculate_ohlcv_for_symbol(self, symbol: str):
        """Calculate weekly and monthly OHLCV for a specific symbol using Python-native dynamic sliding window - replaces all stored procedures"""
        async with self.pool.acquire() as conn:
            try:
                # Get all daily candles for this symbol with their weekly/monthly assignments
                daily_candles = await conn.fetch("""
                SELECT 
                    candle_key_id, symbol, datetime, open, high, low, close, volume,
                    weekly_candle_key_id, monthly_candle_key_id
                FROM daily_candles 
                WHERE symbol = $1
                  AND (weekly_candle_key_id IS NOT NULL OR monthly_candle_key_id IS NOT NULL)
                ORDER BY datetime
                """, symbol)

                if not daily_candles:
                    logger.debug(f"No daily candles found for {symbol} with timeframe assignments")
                    return

                # Group by weekly periods and calculate OHLCV using dynamic sliding window
                weekly_groups = {}
                for candle in daily_candles:
                    if candle['weekly_candle_key_id']:
                        key = candle['weekly_candle_key_id']
                        if key not in weekly_groups:
                            weekly_groups[key] = []
                        weekly_groups[key].append(candle)

                # Group by monthly periods
                monthly_groups = {}
                for candle in daily_candles:
                    if candle['monthly_candle_key_id']:
                        key = candle['monthly_candle_key_id']
                        if key not in monthly_groups:
                            monthly_groups[key] = []
                        monthly_groups[key].append(candle)

                weekly_updates = 0
                monthly_updates = 0

                # Calculate weekly OHLCV with dynamic sliding window
                for weekly_key, group_candles in weekly_groups.items():
                    # Sort by datetime to ensure proper sliding window calculation
                    group_candles.sort(key=lambda x: x['datetime'])

                    for i, current_candle in enumerate(group_candles):
                        # Dynamic sliding window: use all candles from start of week up to current day
                        window_candles = group_candles[:i+1]

                        # Calculate OHLCV for current day's sliding window
                        weekly_open = window_candles[0]['open']  # First day's open
                        weekly_high = max(c['high'] for c in window_candles)  # Max high up to current day
                        weekly_low = min(c['low'] for c in window_candles)   # Min low up to current day
                        weekly_close = current_candle['close']  # Current day's close
                        weekly_volume = sum(c['volume'] for c in window_candles)  # Cumulative volume

                        # Update the current candle with weekly OHLCV
                        await conn.execute("""
                            UPDATE daily_candles
                            SET
                                weekly_open = $1,
                                weekly_high = $2,
                                weekly_low = $3,
                                weekly_close = $4,
                                weekly_volume = $5,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE candle_key_id = $6
                        """, weekly_open, weekly_high, weekly_low, weekly_close,
                            weekly_volume, current_candle['candle_key_id'])
                        weekly_updates += 1

                # Calculate monthly OHLCV with dynamic sliding window
                for monthly_key, group_candles in monthly_groups.items():
                    # Sort by datetime to ensure proper sliding window calculation
                    group_candles.sort(key=lambda x: x['datetime'])

                    for i, current_candle in enumerate(group_candles):
                        # Dynamic sliding window: use all candles from start of month up to current day
                        window_candles = group_candles[:i+1]

                        # Calculate OHLCV for current day's sliding window
                        monthly_open = window_candles[0]['open']  # First day's open
                        monthly_high = max(c['high'] for c in window_candles)  # Max high up to current day
                        monthly_low = min(c['low'] for c in window_candles)   # Min low up to current day
                        monthly_close = current_candle['close']  # Current day's close
                        monthly_volume = sum(c['volume'] for c in window_candles)  # Cumulative volume

                        # Update the current candle with monthly OHLCV
                        await conn.execute("""
                            UPDATE daily_candles
                            SET
                                monthly_open = $1,
                                monthly_high = $2,
                                monthly_low = $3,
                                monthly_close = $4,
                                monthly_volume = $5,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE candle_key_id = $6
                        """, monthly_open, monthly_high, monthly_low, monthly_close,
                            monthly_volume, current_candle['candle_key_id'])
                        monthly_updates += 1

                if weekly_updates > 0 or monthly_updates > 0:
                    logger.debug(f"[SUCCESS] Python-native OHLCV: Updated {weekly_updates} weekly + {monthly_updates} monthly rows for {symbol}")

            except Exception as e:
                # Log error but don't fail the entire data insertion
                logger.warning(f"[WARNING] Python-native OHLCV calculation failed for {symbol}: {e}")
                pass

    async def _check_and_apply_migrations(self):
        """Check and apply database migrations (stored procedures)"""
        try:
            from .database_migration_service import database_migration_service
            
            logger.info("🔍 Checking database migrations...")
            migration_result = await database_migration_service.check_and_apply_migrations()
            
            if migration_result['success']:
                if migration_result['applied']:
                    logger.info(f"✅ Database migration applied: {migration_result['message']}")
                else:
                    logger.debug(f"✅ Database migrations up to date: {migration_result['message']}")
            else:
                logger.error(f"❌ Database migration failed: {migration_result['message']}")
                # Don't raise exception here - let the app continue but log the issue
            
        except Exception as e:
            logger.error(f"❌ Migration check failed: {e}")
            # Don't fail database initialization due to migration issues

    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            self.initialized = False
            logger.info("Ultra-fast database connection pool closed")

# Global instance
ultra_fast_db = UltraFastDatabaseService()