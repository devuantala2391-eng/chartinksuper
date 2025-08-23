"""
High-Speed Database Service V2 - Using JSONB for dynamic indicators
Optimized for unlimited indicator parameters without schema changes
"""

import os
import asyncio
import asyncpg
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class HighSpeedDatabaseServiceV2:
    """
    Improved high-speed database using JSONB for dynamic indicators.
    No more ALTER TABLE operations for new indicators!
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
        
        # Common indicators kept as columns for performance
        self.static_indicators = {
            'rsi_14', 'sma_20', 'sma_50', 'ema_12', 'ema_26',
            'supertrend_10_2', 'supertrend_10_3'
        }

    async def initialize(self):
        """Initialize database with optimized JSONB structure"""
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
                    min_size=5,
                    max_size=20,
                    max_queries=100000,
                    command_timeout=10
                )
                
                # Create optimized table structure
                await self._create_optimized_tables_v2()
                
                self.initialized = True
                logger.info("High-speed database V2 initialized with JSONB support")
                
            except Exception as e:
                logger.error(f"Failed to initialize high-speed database V2: {e}")
                raise

    async def _create_database_if_not_exists(self):
        """Create the high-speed database if it doesn't exist"""
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
                logger.info(f"Created database {self.db_config['database']}")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"Error creating database: {e}")
            raise

    async def _create_optimized_tables_v2(self):
        """Create tables with JSONB for dynamic indicators"""
        async with self.pool.acquire() as conn:
            # Drop old table if migrating
            # await conn.execute("DROP TABLE IF EXISTS daily_candles_old")
            # await conn.execute("ALTER TABLE daily_candles RENAME TO daily_candles_old")
            
            # Create new optimized table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_candles_v2 (
                    symbol VARCHAR(50) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    
                    -- Common indicators as columns for performance
                    rsi_14 DECIMAL(10,4),
                    sma_20 DECIMAL(20,6),
                    sma_50 DECIMAL(20,6),
                    ema_12 DECIMAL(20,6),
                    ema_26 DECIMAL(20,6),
                    supertrend_10_2 DECIMAL(20,6),
                    supertrend_10_3 DECIMAL(20,6),
                    
                    -- JSONB column for all dynamic indicators
                    indicators JSONB DEFAULT '{}',
                    
                    -- Metadata
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            
            # Create indexes for performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_v2_symbol 
                ON daily_candles_v2(symbol)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_v2_timestamp 
                ON daily_candles_v2(timestamp DESC)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_v2_datetime 
                ON daily_candles_v2(datetime DESC)
            """)
            
            # GIN index for JSONB queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_v2_indicators 
                ON daily_candles_v2 USING GIN (indicators)
            """)
            
            # Functional indexes for common JSONB queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_v2_supertrend_30_1dot2 
                ON daily_candles_v2 ((indicators->>'supertrend_30_1dot2'))
                WHERE indicators ? 'supertrend_30_1dot2'
            """)
            
            logger.info("Created optimized tables with JSONB support")

    async def insert_daily_candles_with_indicators(self, symbol: str, candles_with_indicators: List[Dict]) -> bool:
        """Insert candles with dynamic indicators using JSONB"""
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
                    
                    # Extract static indicators
                    for indicator in ['rsi_14', 'sma_20', 'sma_50', 'ema_12', 'ema_26', 'supertrend_10_2', 'supertrend_10_3']:
                        row_values.append(candle.get(indicator))
                    
                    # Extract dynamic indicators into JSONB
                    dynamic_indicators = {}
                    for key, value in candle.items():
                        # Skip base fields and static indicators
                        if key not in ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume'] \
                           and key not in self.static_indicators \
                           and value is not None:
                            # Store in JSONB
                            dynamic_indicators[key] = value
                    
                    # Add JSONB data
                    row_values.append(json.dumps(dynamic_indicators))
                    values.append(tuple(row_values))
                
                # Bulk insert with UPSERT
                query = """
                    INSERT INTO daily_candles_v2 (
                        symbol, timestamp, datetime, open, high, low, close, volume,
                        rsi_14, sma_20, sma_50, ema_12, ema_26, supertrend_10_2, supertrend_10_3,
                        indicators
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
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
                        indicators = EXCLUDED.indicators,
                        updated_at = CURRENT_TIMESTAMP
                """
                
                await conn.executemany(query, values)
                
                logger.debug(f"Saved {len(candles_with_indicators)} candles for {symbol} with JSONB indicators")
                return True
                
        except Exception as e:
            logger.error(f"Error inserting candles for {symbol}: {e}")
            return False

    async def query_with_indicator(self, indicator_name: str, operator: str, value: float, 
                                  symbols: List[str] = None) -> List[Dict]:
        """
        Query stocks based on dynamic indicator values.
        
        Example: Find all stocks where supertrend_30_1dot2 > 100
        """
        try:
            async with self.pool.acquire() as conn:
                # Build the query based on whether it's a static or dynamic indicator
                if indicator_name in self.static_indicators:
                    # Query static column
                    base_query = f"""
                        SELECT symbol, timestamp, close, {indicator_name}
                        FROM daily_candles_v2
                        WHERE {indicator_name} {operator} $1
                    """
                else:
                    # Query JSONB column
                    base_query = f"""
                        SELECT symbol, timestamp, close, 
                               (indicators->>'{indicator_name}')::numeric as {indicator_name}
                        FROM daily_candles_v2
                        WHERE (indicators->>'{indicator_name}')::numeric {operator} $1
                    """
                
                # Add symbol filter if provided
                if symbols:
                    base_query += f" AND symbol = ANY($2)"
                    results = await conn.fetch(base_query, value, symbols)
                else:
                    results = await conn.fetch(base_query, value)
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Query error for {indicator_name}: {e}")
            return []

    async def get_latest_with_indicators(self, symbols: List[str], 
                                        indicator_names: List[str]) -> Dict[str, Dict]:
        """
        Get latest values for multiple symbols with specific indicators.
        Optimized for real-time queries.
        """
        try:
            async with self.pool.acquire() as conn:
                # Build dynamic SELECT clause
                select_parts = ['symbol', 'timestamp', 'close']
                
                for indicator in indicator_names:
                    if indicator in self.static_indicators:
                        select_parts.append(indicator)
                    else:
                        select_parts.append(f"(indicators->>'{indicator}')::numeric as {indicator}")
                
                query = f"""
                    SELECT DISTINCT ON (symbol) {', '.join(select_parts)}
                    FROM daily_candles_v2
                    WHERE symbol = ANY($1)
                    ORDER BY symbol, timestamp DESC
                """
                
                results = await conn.fetch(query, symbols)
                
                return {row['symbol']: dict(row) for row in results}
                
        except Exception as e:
            logger.error(f"Error getting latest values: {e}")
            return {}

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        async with self.pool.acquire() as conn:
            yield conn

# Global instance
high_speed_db_v2 = HighSpeedDatabaseServiceV2()