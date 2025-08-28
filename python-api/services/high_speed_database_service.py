"""
High-Speed Database Service for Stock Data V2
Optimized with JSONB for unlimited dynamic indicators without schema changes
"""

import os
import asyncio
import asyncpg
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from pathlib import Path
from decimal import Decimal

# Custom JSON encoder to handle Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

load_dotenv()
logger = logging.getLogger(__name__)

class HighSpeedDatabaseService:
    """
    Ultra-fast database service with JSONB for dynamic indicators.
    No more ALTER TABLE operations - unlimited indicator support!
    """
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        self.pool = None
        self.initialized = False
        self._init_lock = asyncio.Lock()
        
        # Optimized batch sizes for different operations
        self.batch_sizes = {
            'daily_insert': 1000,
            'weekly_insert': 500, 
            'monthly_insert': 100,
            'indicator_calculation': 50,
        }
        
        # Load static indicators from config
        self.schema_config = self._load_schema_config()
        self.static_indicators = self._get_static_indicators_set()

    async def initialize(self):
        """Initialize the high-speed database with optimized settings"""
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
                    min_size=5,          # Always ready connections
                    max_size=20,         # Scale for heavy load
                    max_queries=100000,  # High query limit
                    max_inactive_connection_lifetime=5,  # Fast turnover
                    command_timeout=10,  # Quick timeout
                    connection_class=asyncpg.Connection,
                    setup=self._setup_connection,
                    server_settings={
                        'application_name': 'high_speed_nse_service',
                        'jit': 'off'
                    }
                )
                
                # Create optimized table structure from config
                await self._create_optimized_tables()
                await self._migrate_schema_if_needed()
                await self._create_speed_indexes()
                
                self.initialized = True
                logger.info("High-speed database service initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize high-speed database: {e}")
                raise

    async def health_check(self) -> bool:
        """Perform a health check on the database connection"""
        if not self.initialized or not self.pool:
            return False
        
        try:
            async with asyncio.timeout(3):
                async with self.pool.acquire() as conn:
                    result = await conn.fetchval("SELECT 1")
                    return result == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_all_symbols(self) -> List[str]:
        """Get list of all symbols in the database"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT symbol 
                    FROM symbols_config 
                    ORDER BY symbol
                """)
                return [row['symbol'] for row in rows]
        except Exception as e:
            logger.error(f"Error getting all symbols: {e}")
            return []

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Get basic stats
                daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles") or 0
                weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles") or 0
                monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles") or 0
                symbols_count = await conn.fetchval("SELECT COUNT(*) FROM symbols_config") or 0
                
                return {
                    'daily_candles': daily_count,
                    'weekly_candles': weekly_count,
                    'monthly_candles': monthly_count,
                    'total_symbols': symbols_count,
                    'status': 'active'
                }
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {'status': 'error', 'error': str(e)}

    def _load_schema_config(self) -> Dict:
        """Load schema configuration from config file"""
        config_path = Path(__file__).parent.parent / 'config' / 'schema_indicators.json'
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Schema config not found at {config_path}, using defaults")
                return self._get_default_schema_config()
        except Exception as e:
            logger.error(f"Error loading schema config: {e}")
            return self._get_default_schema_config()
    
    def _get_default_schema_config(self) -> Dict:
        """Get default schema configuration"""
        return {
            "static_indicators": {
                "daily_candles": [
                    {"column_name": "rsi_14", "data_type": "DECIMAL(10,4)"},
                    {"column_name": "sma_20", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "sma_50", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "ema_12", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "ema_26", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "supertrend_10_2", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "supertrend_10_3", "data_type": "DECIMAL(20,6)"},
                    {"column_name": "supertrend_signal_10_2", "data_type": "INTEGER"},
                    {"column_name": "supertrend_signal_10_3", "data_type": "INTEGER"}
                ]
            }
        }
    
    def _get_static_indicators_set(self) -> set:
        """Get set of static indicator column names"""
        indicators = set()
        for table_name in ['daily_candles', 'weekly_candles', 'monthly_candles']:
            if table_name in self.schema_config.get('static_indicators', {}):
                for indicator in self.schema_config['static_indicators'][table_name]:
                    indicators.add(indicator['column_name'])
        return indicators
    
    async def _setup_connection(self, connection):
        """Setup each connection for maximum performance"""
        # Optimized settings for speed (only session-level settings)
        await connection.execute("SET statement_timeout = '10s'")
        await connection.execute("SET idle_in_transaction_session_timeout = '3s'")
        await connection.execute("SET lock_timeout = '2s'")
        await connection.execute("SET synchronous_commit = off")

    async def _create_table_from_schema(self, conn, table_name: str):
        """Create table using schema configuration"""
        if table_name == 'daily_candles':
            # Build CREATE TABLE statement from schema
            columns = [
                "symbol VARCHAR(50) NOT NULL",
                "timestamp BIGINT NOT NULL",
                "datetime TIMESTAMP NOT NULL",
                "open DECIMAL(20,6) NOT NULL",
                "high DECIMAL(20,6) NOT NULL",
                "low DECIMAL(20,6) NOT NULL",
                "close DECIMAL(20,6) NOT NULL",
                "volume BIGINT NOT NULL"
            ]
            
            # Add static indicator columns from config
            if 'daily_candles' in self.schema_config.get('static_indicators', {}):
                for indicator in self.schema_config['static_indicators']['daily_candles']:
                    columns.append(f"{indicator['column_name']} {indicator['data_type']}")
            
            # Add JSONB column for dynamic indicators
            columns.append("indicators JSONB DEFAULT '{}'")
            
            # Add metadata columns
            columns.append("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            columns.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    {','.join(columns)},
                    PRIMARY KEY (symbol, timestamp)
                )
            """
            
            await conn.execute(create_sql)
            logger.info(f"Created table {table_name} with {len(columns)} columns")
    
    async def _migrate_schema_if_needed(self):
        """Check and apply schema migrations for new columns"""
        async with self.pool.acquire() as conn:
            for table_name in ['daily_candles', 'weekly_candles', 'monthly_candles']:
                # Check if table exists
                table_exists = await conn.fetchval(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table_name}'
                    )
                """)
                
                if not table_exists:
                    continue
                    
                # Get existing columns
                existing_columns = await self._get_table_columns(conn, table_name)
                
                # Get required columns from config
                required_columns = set()
                if table_name in self.schema_config.get('static_indicators', {}):
                    for indicator in self.schema_config['static_indicators'][table_name]:
                        required_columns.add(indicator['column_name'])
                
                # Find missing columns
                missing_columns = required_columns - set(existing_columns)
                
                # Add missing columns
                if missing_columns:
                    logger.info(f"Adding {len(missing_columns)} new columns to {table_name}: {missing_columns}")
                    for col_name in missing_columns:
                        # Find column definition from config
                        col_def = None
                        for indicator in self.schema_config['static_indicators'][table_name]:
                            if indicator['column_name'] == col_name:
                                col_def = indicator
                                break
                        
                        if col_def:
                            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_def['column_name']} {col_def['data_type']}"
                            await conn.execute(alter_sql)
                            logger.info(f"Added column {col_def['column_name']} to {table_name}")
    
    async def _create_database_if_not_exists(self):
        """Create the high-speed database if it doesn't exist"""
        default_config = self.db_config.copy()
        default_config['database'] = 'postgres'
        
        conn = None
        try:
            conn = await asyncpg.connect(**default_config)
            db_exists = await conn.fetchval(
                f"SELECT 1 FROM pg_database WHERE datname = '{self.db_config['database']}'"
            )
            
            if not db_exists:
                await conn.execute(f'CREATE DATABASE "{self.db_config["database"]}"')
                logger.info(f"Created database: {self.db_config['database']}")
                
        finally:
            if conn:
                await conn.close()

    async def _create_optimized_tables(self):
        """Create optimized table structure with JSONB for dynamic indicators"""
        async with self.pool.acquire() as conn:
            # Drop old unnecessary tables
            logger.info("Cleaning up old tables...")
            
            # Drop old file-based storage tables if they exist
            await conn.execute("DROP TABLE IF EXISTS precalculated_storage CASCADE")
            await conn.execute("DROP TABLE IF EXISTS mapper_storage CASCADE")
            await conn.execute("DROP TABLE IF EXISTS file_based_cache CASCADE")
            
            # Drop old weekly and monthly tables (we'll use views instead if needed)
            await conn.execute("DROP TABLE IF EXISTS weekly_candles CASCADE")
            await conn.execute("DROP TABLE IF EXISTS monthly_candles CASCADE")
            
            # Drop old latest_values table (will use materialized view)
            await conn.execute("DROP TABLE IF EXISTS latest_values CASCADE")
            
            # Backup existing daily_candles if migrating
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'daily_candles'
                    AND table_schema = 'public'
                )
            """)
            
            if table_exists:
                # Check if it's the old structure (has many columns)
                column_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'daily_candles'
                """)
                
                if column_count > 20:  # Old structure has many indicator columns
                    logger.info("Migrating from old table structure...")
                    await conn.execute("DROP TABLE IF EXISTS daily_candles_old CASCADE")
                    await conn.execute("ALTER TABLE daily_candles RENAME TO daily_candles_old")
            
            # Create new optimized table with JSONB using schema config
            await self._create_table_from_schema(conn, 'daily_candles')

            # Weekly candles with pre-calculated indicators
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_candles (
                    symbol VARCHAR(20) NOT NULL,
                    week_start_timestamp BIGINT NOT NULL,
                    week_start_date DATE NOT NULL,
                    
                    -- Weekly OHLCV
                    open DECIMAL(12,4) NOT NULL,
                    high DECIMAL(12,4) NOT NULL,
                    low DECIMAL(12,4) NOT NULL,
                    close DECIMAL(12,4) NOT NULL,
                    volume BIGINT NOT NULL,
                    trading_days INTEGER NOT NULL,
                    
                    -- Weekly Technical Indicators
                    rsi_14 DECIMAL(8,4),
                    rsi_21 DECIMAL(8,4),
                    sma_10 DECIMAL(12,4),
                    sma_20 DECIMAL(12,4),
                    ema_12 DECIMAL(12,4),
                    ema_26 DECIMAL(12,4),
                    
                    -- Weekly SuperTrend
                    supertrend_10_2 DECIMAL(12,4),
                    supertrend_signal_10_2 INTEGER,
                    supertrend_10_3 DECIMAL(12,4),
                    supertrend_signal_10_3 INTEGER,
                    
                    -- Weekly Bollinger Bands
                    bb_upper_20_2 DECIMAL(12,4),
                    bb_middle_20_2 DECIMAL(12,4),
                    bb_lower_20_2 DECIMAL(12,4),
                    
                    -- Weekly Performance
                    change_1w DECIMAL(8,4),
                    change_4w DECIMAL(8,4),
                    change_12w DECIMAL(8,4),
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (symbol, week_start_timestamp)
                )
            """)

            # Monthly candles with pre-calculated indicators
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_candles (
                    symbol VARCHAR(20) NOT NULL,
                    month_start_timestamp BIGINT NOT NULL,
                    month_start_date DATE NOT NULL,
                    
                    -- Monthly OHLCV
                    open DECIMAL(12,4) NOT NULL,
                    high DECIMAL(12,4) NOT NULL,
                    low DECIMAL(12,4) NOT NULL,
                    close DECIMAL(12,4) NOT NULL,
                    volume BIGINT NOT NULL,
                    trading_days INTEGER NOT NULL,
                    
                    -- Monthly Technical Indicators
                    rsi_14 DECIMAL(8,4),
                    rsi_21 DECIMAL(8,4),
                    sma_10 DECIMAL(12,4),
                    sma_20 DECIMAL(12,4),
                    ema_12 DECIMAL(12,4),
                    ema_26 DECIMAL(12,4),
                    
                    -- Monthly SuperTrend
                    supertrend_10_2 DECIMAL(12,4),
                    supertrend_signal_10_2 INTEGER,
                    supertrend_10_3 DECIMAL(12,4),
                    supertrend_signal_10_3 INTEGER,
                    
                    -- Monthly Bollinger Bands
                    bb_upper_20_2 DECIMAL(12,4),
                    bb_middle_20_2 DECIMAL(12,4),
                    bb_lower_20_2 DECIMAL(12,4),
                    
                    -- Monthly Performance
                    change_1m DECIMAL(8,4),
                    change_3m DECIMAL(8,4),
                    change_6m DECIMAL(8,4),
                    change_12m DECIMAL(8,4),
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (symbol, month_start_timestamp)
                )
            """)

            # Latest values cache for instant access
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS latest_values (
                    symbol VARCHAR(20) PRIMARY KEY,
                    
                    -- Latest Daily Values
                    latest_timestamp BIGINT NOT NULL,
                    latest_close DECIMAL(12,4) NOT NULL,
                    latest_volume BIGINT NOT NULL,
                    
                    -- Latest Weekly Values
                    latest_weekly_close DECIMAL(12,4),
                    latest_weekly_timestamp BIGINT,
                    
                    -- Latest Monthly Values
                    latest_monthly_close DECIMAL(12,4),
                    latest_monthly_timestamp BIGINT,
                    
                    -- Real-time Performance
                    change_1d DECIMAL(8,4),
                    change_7d DECIMAL(8,4),
                    change_30d DECIMAL(8,4),
                    
                    -- Latest Signals
                    daily_supertrend_signal INTEGER,
                    weekly_supertrend_signal INTEGER,
                    monthly_supertrend_signal INTEGER,
                    
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Symbol configuration and metadata
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbols_config (
                    symbol VARCHAR(20) PRIMARY KEY,
                    is_active BOOLEAN DEFAULT true,
                    last_daily_update TIMESTAMP,
                    last_weekly_update TIMESTAMP,
                    last_monthly_update TIMESTAMP,
                    total_daily_candles INTEGER DEFAULT 0,
                    total_weekly_candles INTEGER DEFAULT 0,
                    total_monthly_candles INTEGER DEFAULT 0,
                    first_trading_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def _create_speed_indexes(self):
        """Create optimized indexes for maximum query speed with JSONB support"""
        async with self.pool.acquire() as conn:
            
            # Daily Candles Indexes
            indexes = [
                # Primary indexes for performance
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_symbol_timestamp ON daily_candles (symbol, timestamp DESC)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_timestamp ON daily_candles (timestamp DESC)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_symbol ON daily_candles (symbol)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_datetime ON daily_candles (datetime DESC)",
                
                # OHLCV indexes
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_close ON daily_candles (close)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_volume ON daily_candles (volume DESC)",
                
                # Static indicator indexes
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_supertrend_signal ON daily_candles (supertrend_signal_10_2) WHERE supertrend_signal_10_2 IS NOT NULL",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_rsi ON daily_candles (rsi_14) WHERE rsi_14 IS NOT NULL",
                
                # JSONB GIN index for fast indicator queries
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_indicators ON daily_candles USING GIN (indicators)",
                
                # Functional indexes for commonly queried JSONB fields
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_supertrend_30_1dot2 ON daily_candles ((indicators->>'supertrend_30_1dot2')) WHERE indicators ? 'supertrend_30_1dot2'",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_supertrend_30_5 ON daily_candles ((indicators->>'supertrend_30_5')) WHERE indicators ? 'supertrend_30_5'",
                
                # Composite index for complex queries
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_symbol_close_volume ON daily_candles (symbol, close DESC, volume DESC)",
            ]
            
            for index_sql in indexes:
                try:
                    await conn.execute(index_sql)
                except Exception as e:
                    # Ignore if index already exists
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Index creation warning: {e}")

    async def _get_table_columns(self, conn, table_name: str) -> List[str]:
        """Get list of all columns in a table"""
        try:
            rows = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = $1 
                ORDER BY ordinal_position
            """, table_name)
            return [row['column_name'] for row in rows]
        except Exception as e:
            logger.error(f"Error getting table columns for {table_name}: {e}")
            return []


    # ===============================
    # HIGH-SPEED DATA INSERTION
    # ===============================

    async def insert_daily_candles_with_indicators(self, symbol: str, candles_with_indicators: List[Dict]) -> bool:
        """Insert daily candles with indicators using JSONB - NO ALTER TABLE needed!"""
        try:
            if not candles_with_indicators:
                return True
                
            async with self.pool.acquire() as conn:
                # Prepare data for bulk insert
                values = []
                for candle in candles_with_indicators:
                    # Extract base OHLCV data
                    row_values = [
                        symbol,
                        candle['timestamp'],
                        datetime.utcfromtimestamp(candle['timestamp'] / 1000),
                        float(candle['open']),
                        float(candle['high']),
                        float(candle['low']),
                        float(candle['close']),
                        int(candle['volume'])
                    ]
                    
                    # Extract static indicators (commonly used ones)
                    for indicator in ['rsi_14', 'sma_20', 'sma_50', 'ema_12', 'ema_26', 
                                    'supertrend_10_2', 'supertrend_10_3', 
                                    'supertrend_signal_10_2', 'supertrend_signal_10_3']:
                        row_values.append(candle.get(indicator))
                    
                    # Extract ALL other indicators into JSONB
                    dynamic_indicators = {}
                    base_fields = {'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'symbol'}
                    
                    for key, value in candle.items():
                        # Skip base fields and static indicators
                        if key not in base_fields and key not in self.static_indicators and value is not None:
                            # Convert datetime objects to ISO string for JSON serialization
                            if isinstance(value, datetime):
                                value = value.isoformat()
                            # Store in JSONB (includes decimal parameter indicators like supertrend_30_1dot2)
                            dynamic_indicators[key] = value
                    
                    # Add JSONB data
                    row_values.append(json.dumps(dynamic_indicators) if dynamic_indicators else '{}')
                    values.append(tuple(row_values))
                
                # Find monthly relationships for all candles
                monthly_assignments = await self._find_monthly_assignments_for_daily_candles(
                    conn, [(candle['symbol'], candle['datetime']) for candle in candles_with_indicators]
                )
                
                # Add monthly_key and monthly_candle_key_id to values
                for i, candle in enumerate(candles_with_indicators):
                    monthly_key, monthly_candle_key_id = monthly_assignments.get(
                        (candle['symbol'], candle['datetime']), (None, None)
                    )
                    # Extend the row_values for this candle with monthly fields
                    values[i] = values[i] + (monthly_key, monthly_candle_key_id)
                
                # Bulk insert with UPSERT
                query = """
                    INSERT INTO daily_candles (
                        symbol, timestamp, datetime, open, high, low, close, volume,
                        rsi_14, sma_20, sma_50, ema_12, ema_26,
                        supertrend_10_2, supertrend_10_3,
                        supertrend_signal_10_2, supertrend_signal_10_3,
                        indicators, monthly_key, monthly_candle_key_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
                    ON CONFLICT (symbol, timestamp) DO UPDATE SET
                        datetime = EXCLUDED.datetime,
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        rsi_14 = EXCLUDED.rsi_14,
                        sma_20 = EXCLUDED.sma_20,
                        sma_50 = EXCLUDED.sma_50,
                        ema_12 = EXCLUDED.ema_12,
                        ema_26 = EXCLUDED.ema_26,
                        supertrend_10_2 = EXCLUDED.supertrend_10_2,
                        supertrend_10_3 = EXCLUDED.supertrend_10_3,
                        supertrend_signal_10_2 = EXCLUDED.supertrend_signal_10_2,
                        supertrend_signal_10_3 = EXCLUDED.supertrend_signal_10_3,
                        indicators = EXCLUDED.indicators,
                        monthly_key = EXCLUDED.monthly_key,
                        monthly_candle_key_id = EXCLUDED.monthly_candle_key_id,
                        updated_at = CURRENT_TIMESTAMP
                """
                
                await conn.executemany(query, values)
                
                logger.debug(f"Saved {len(candles_with_indicators)} candles with JSONB indicators for {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"Error inserting candles for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _find_monthly_assignments_for_daily_candles(self, conn, candle_refs: List[Tuple[str, datetime]]) -> Dict[Tuple[str, datetime], Tuple[int, str]]:
        """Find monthly_key and monthly_candle_key_id for daily candles based on their date"""
        assignments = {}
        
        # Get all monthly candles for the symbols we need
        symbols = list(set(ref[0] for ref in candle_refs))
        
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
            monthly_key = None
            monthly_candle_key_id = None
            
            for mc in monthly_candles:
                if (mc['symbol'] == symbol and 
                    mc['month_start_datetime'].date() <= candle_date <= mc['month_end_datetime'].date()):
                    monthly_key = mc['month_sequence_number']
                    monthly_candle_key_id = mc['monthly_candle_key_id']
                    break
            
            assignments[(symbol, candle_datetime)] = (monthly_key, monthly_candle_key_id)
        
        return assignments

    # ===============================
    # ULTRA-FAST QUERY METHODS
    # ===============================
    
    async def query_with_jsonb_indicator(self, indicator_name: str, operator: str, value: float, 
                                         symbols: List[str] = None, limit: int = None) -> List[Dict]:
        """
        Query stocks based on JSONB indicator values - SUPER FAST!
        
        Example: Find all stocks where supertrend_30_1dot2 > 100
        """
        try:
            async with self.pool.acquire() as conn:
                # Check if it's a static indicator or dynamic (JSONB)
                if indicator_name in self.static_indicators:
                    # Query static column
                    base_query = f"""
                        SELECT symbol, timestamp, close, {indicator_name}
                        FROM daily_candles
                        WHERE {indicator_name} {operator} $1
                    """
                    params = [value]
                else:
                    # Query JSONB column - PostgreSQL automatically uses GIN index
                    base_query = f"""
                        SELECT symbol, timestamp, close, 
                               (indicators->>'{indicator_name}')::numeric as {indicator_name}
                        FROM daily_candles
                        WHERE (indicators->>'{indicator_name}')::numeric {operator} $1
                    """
                    params = [value]
                
                # Add symbol filter if provided
                if symbols:
                    base_query += f" AND symbol = ANY(${len(params)+1})"
                    params.append(symbols)
                
                # Add ordering and limit
                base_query += " ORDER BY timestamp DESC"
                if limit:
                    base_query += f" LIMIT ${len(params)+1}"
                    params.append(limit)
                
                results = await conn.fetch(base_query, *params)
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Query error for {indicator_name}: {e}")
            return []

    async def get_latest_values_multiple(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get latest values for multiple symbols in single query (< 1ms)"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT symbol, latest_close, change_1d, change_7d, change_30d,
                           daily_supertrend_signal, weekly_supertrend_signal, monthly_supertrend_signal,
                           latest_volume, updated_at
                    FROM latest_values 
                    WHERE symbol = ANY($1)
                """, symbols)
                
                return {
                    row['symbol']: {
                        'close': float(row['latest_close']),
                        'change_1d': float(row['change_1d']) if row['change_1d'] else None,
                        'change_7d': float(row['change_7d']) if row['change_7d'] else None,
                        'change_30d': float(row['change_30d']) if row['change_30d'] else None,
                        'daily_signal': row['daily_supertrend_signal'],
                        'weekly_signal': row['weekly_supertrend_signal'],
                        'monthly_signal': row['monthly_supertrend_signal'],
                        'volume': int(row['latest_volume']),
                        'updated_at': row['updated_at']
                    }
                    for row in rows
                }
                
        except Exception as e:
            logger.error(f"Error getting latest values: {e}")
            return {}

    async def get_daily_candles_with_indicators(self, symbol: str, limit: int = 500) -> List[Dict]:
        """Get daily candles with all indicators (< 10ms)"""
        try:
            async with self.pool.acquire() as conn:
                # Get actual columns from the table
                columns = await self._get_table_columns(conn, 'daily_candles')
                
                # Build column list, excluding system columns
                exclude_columns = {'created_at', 'updated_at'}
                select_columns = [col for col in columns if col not in exclude_columns]
                
                # Build query with actual columns
                column_list = ', '.join(select_columns)
                query = f"""
                    SELECT {column_list}
                    FROM daily_candles 
                    WHERE symbol = $1 
                    ORDER BY timestamp DESC 
                    LIMIT $2
                """
                
                rows = await conn.fetch(query, symbol, limit)
                
                # Convert rows to list of dicts, expanding JSONB indicators
                result = []
                for row in rows:
                    row_dict = dict(row)
                    
                    # Expand indicators from JSONB if present
                    if 'indicators' in row_dict and row_dict['indicators']:
                        indicators = row_dict.pop('indicators')
                        if isinstance(indicators, dict):
                            row_dict.update(indicators)
                    
                    result.append(row_dict)
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting daily candles for {symbol}: {e}")
            return []

    async def screen_stocks_by_signals(self, timeframe: str = 'daily', signal_value: int = 1) -> List[Dict]:
        """Screen stocks by SuperTrend signals (< 5ms for 1000+ stocks)"""
        try:
            table_name = f"{timeframe}_candles"
            timestamp_col = 'timestamp' if timeframe == 'daily' else f"{timeframe.replace('ly', '')}_start_timestamp"
            
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    query = """
                        SELECT symbol, close, supertrend_signal_10_2, rsi_14, volume
                        FROM daily_candles 
                        WHERE timestamp = (
                            SELECT MAX(timestamp) FROM daily_candles WHERE symbol = daily_candles.symbol
                        )
                        AND supertrend_signal_10_2 = $1
                        ORDER BY close DESC
                    """
                else:
                    query = f"""
                        SELECT symbol, close, supertrend_signal_10_2, rsi_14, volume
                        FROM {table_name}
                        WHERE {timestamp_col} = (
                            SELECT MAX({timestamp_col}) FROM {table_name} WHERE symbol = {table_name}.symbol
                        )
                        AND supertrend_signal_10_2 = $1
                        ORDER BY close DESC
                    """
                
                rows = await conn.fetch(query, signal_value)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error screening stocks: {e}")
            return []

    async def _update_latest_values_cache(self, symbol: str, latest_candle: Dict):
        """Update the latest values cache for instant access"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO latest_values (
                        symbol, latest_timestamp, latest_close, latest_volume,
                        change_1d, change_7d, change_30d, daily_supertrend_signal
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol) DO UPDATE SET
                        latest_timestamp = EXCLUDED.latest_timestamp,
                        latest_close = EXCLUDED.latest_close,
                        latest_volume = EXCLUDED.latest_volume,
                        change_1d = EXCLUDED.change_1d,
                        change_7d = EXCLUDED.change_7d,
                        change_30d = EXCLUDED.change_30d,
                        daily_supertrend_signal = EXCLUDED.daily_supertrend_signal,
                        updated_at = CURRENT_TIMESTAMP
                """, 
                symbol,
                latest_candle['timestamp'],
                float(latest_candle['close']),
                int(latest_candle['volume']),
                latest_candle.get('change_1d'),
                latest_candle.get('change_7d'),
                latest_candle.get('change_30d'),
                latest_candle.get('supertrend_signal_10_2')
                )
                
        except Exception as e:
            logger.error(f"Error updating latest values cache for {symbol}: {e}")

    async def populate_from_nse_database(self) -> Dict[str, int]:
        """
        Populate high-speed database from NSE database.
        Reads data from individual stock tables and consolidates into daily_candles table.
        
        Returns:
            Dictionary with statistics about the population process
        """
        try:
            logger.info("Starting population of high-speed database from NSE database")
            
            if not self.pool:
                await self.initialize()
            
            # Get connection to NSE database
            nse_pool = await asyncpg.create_pool(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database='nse',
                min_size=2,
                max_size=10
            )
            
            stats = {
                'total_stocks': 0,
                'successful': 0,
                'failed': 0,
                'total_candles': 0
            }
            
            try:
                async with nse_pool.acquire() as nse_conn:
                    # Get all stock tables (excluding metadata table)
                    tables = await nse_conn.fetch("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name LIKE 'stock_%'
                        AND table_name != 'stock_metadata'
                        ORDER BY table_name
                    """)
                    
                    stats['total_stocks'] = len(tables)
                    logger.info(f"Found {len(tables)} stock tables to process")
                    
                    # Process each stock table
                    for table_row in tables:
                        table_name = table_row['table_name']
                        symbol = table_name.replace('stock_', '').upper()
                        
                        try:
                            # Read candles from NSE database
                            candles = await nse_conn.fetch(f"""
                                SELECT * FROM {table_name}
                                ORDER BY timestamp DESC
                            """)
                            
                            if candles:
                                # Convert to list of dicts
                                candle_dicts = []
                                for candle in candles:
                                    candle_dict = dict(candle)
                                    # Ensure symbol is set
                                    candle_dict['symbol'] = symbol
                                    candle_dicts.append(candle_dict)
                                
                                # Calculate static indicators before inserting
                                from services.static_indicator_calculator import static_indicator_calculator
                                candle_dicts = static_indicator_calculator.calculate_static_indicators(candle_dicts, 'daily_candles')
                                
                                # Insert into high-speed database with calculated indicators
                                success = await self.insert_daily_candles_with_indicators(symbol, candle_dicts)
                                
                                if success:
                                    stats['successful'] += 1
                                    stats['total_candles'] += len(candles)
                                    if stats['successful'] % 100 == 0:
                                        logger.info(f"Processed {stats['successful']} stocks...")
                                else:
                                    stats['failed'] += 1
                                    logger.warning(f"Failed to insert data for {symbol}")
                            else:
                                logger.debug(f"No data found for {symbol}")
                                stats['failed'] += 1  # Count as failed if no data
                                
                        except Exception as e:
                            stats['failed'] += 1
                            logger.error(f"Error processing {symbol} from table {table_name}: {e}")
                            # Log first error in detail
                            if stats['failed'] == 1:
                                import traceback
                                logger.error(f"First error details: {traceback.format_exc()}")
                    
                    logger.info(f"High-speed database population completed: {stats}")
                    
            finally:
                await nse_pool.close()
                
            return stats
            
        except Exception as e:
            logger.error(f"Failed to populate high-speed database: {e}")
            raise

    async def update_indicator_in_jsonb(self, symbol: str, indicator_key: str, indicator_values: List[Dict]) -> bool:
        """
        Update a specific indicator in the JSONB column for a symbol.
        
        Args:
            symbol: Stock symbol
            indicator_key: Key for the indicator (e.g., 'supertrend_10_1dot2')
            indicator_values: List of dicts with timestamp and indicator value
            
        Returns:
            True if successful
        """
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                # Update indicators in JSONB for each candle
                for value_dict in indicator_values:
                    timestamp = value_dict.get('timestamp')
                    value = value_dict.get('value')
                    
                    if timestamp is not None and value is not None:
                        # Convert value to float if it's a Decimal
                        if isinstance(value, Decimal):
                            value = float(value)
                        
                        # Update JSONB by adding/updating the specific indicator
                        await conn.execute("""
                            UPDATE daily_candles
                            SET indicators = jsonb_set(
                                COALESCE(indicators, '{}'),
                                $1::text[],
                                $2::jsonb
                            )
                            WHERE symbol = $3 AND timestamp = $4
                        """, [indicator_key], json.dumps(value, cls=DecimalEncoder), symbol, timestamp)
                
                logger.info(f"Updated {indicator_key} for {symbol} - {len(indicator_values)} values")
                return True
                
        except Exception as e:
            logger.error(f"Error updating indicator {indicator_key} for {symbol}: {e}")
            return False
    
    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            self.initialized = False
            logger.info("High-speed database connection pool closed")

# Global instance for high-speed operations
high_speed_db = HighSpeedDatabaseService()