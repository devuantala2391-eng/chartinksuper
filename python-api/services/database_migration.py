"""
Database Migration Script for Ultra-Fast Pipeline
- Migrates from old (symbol, timestamp) primary key to new composite key system
- Adds proper composite_key_id column (20MICRONS_1, 20MICRONS_2, etc.)
- Creates symbol_metadata table for latest key tracking
- Maintains all existing data while adding optimizations
"""

import asyncio
import asyncpg
import logging
import os
from typing import Dict, List, Any
from dotenv import load_dotenv
import json

load_dotenv()
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """
    Handles migration from old database structure to new ultra-fast composite key system.
    """
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        # Target database - we'll migrate nse_highspeed to new structure
        self.target_database = 'nse_highspeed'
        
        logger.info("🔧 Database migrator initialized for ultra-fast pipeline")

    async def run_full_migration(self):
        """Run complete migration from old to new structure"""
        logger.info("🚀 Starting database migration to ultra-fast composite key system")
        
        # Step 1: Backup existing data
        await self.backup_existing_data()
        
        # Step 2: Create new structure
        await self.create_new_structure()
        
        # Step 3: Migrate existing data with composite keys
        await self.migrate_existing_data()
        
        # Step 4: Create indexes and constraints
        await self.create_optimized_indexes()
        
        # Step 5: Validate migration
        await self.validate_migration()
        
        logger.info("✅ Migration completed successfully!")

    async def backup_existing_data(self):
        """Create backup of existing data before migration"""
        logger.info("💾 Creating backup of existing data...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            # Create backup tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_candles_backup AS 
                SELECT * FROM daily_candles
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_candles_backup AS 
                SELECT * FROM weekly_candles
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monthly_candles_backup AS 
                SELECT * FROM monthly_candles
            """)
            
            # Count records for validation
            daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles_backup")
            weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles_backup")
            monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles_backup")
            
            logger.info(f"✅ Backed up {daily_count} daily, {weekly_count} weekly, {monthly_count} monthly candles")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            raise

    async def create_new_structure(self):
        """Create new table structure with composite keys"""
        logger.info("🏗️ Creating new ultra-fast table structure...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            # Drop old primary key constraints and recreate tables with new structure
            timeframes = ['daily', 'weekly', 'monthly']
            
            for timeframe in timeframes:
                table_name = f"{timeframe}_candles"
                
                logger.info(f"🔧 Migrating {table_name} to new structure...")
                
                # Drop existing table and recreate with new structure
                await conn.execute(f"DROP TABLE IF EXISTS {table_name}_new")
                
                await conn.execute(f"""
                    CREATE TABLE {table_name}_new (
                        -- New composite primary key column
                        candle_key_id VARCHAR(50) PRIMARY KEY,     -- 20MICRONS_1, 20MICRONS_2, etc.
                        
                        -- Symbol and key components (for queries and reference)
                        symbol VARCHAR(20) NOT NULL,
                        candle_sequence_number INTEGER NOT NULL,   -- 0, 1, 2, 3... (sequence within symbol)
                        
                        -- Original timestamp data
                        timestamp BIGINT NOT NULL,
                        datetime TIMESTAMP NOT NULL,
                        
                        -- OHLCV data
                        open DECIMAL(20,6) NOT NULL,
                        high DECIMAL(20,6) NOT NULL,
                        low DECIMAL(20,6) NOT NULL,
                        close DECIMAL(20,6) NOT NULL,
                        volume BIGINT NOT NULL,
                        
                        -- All indicators stored in JSONB for flexibility
                        indicators JSONB DEFAULT '{{}}',
                        
                        -- Metadata
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                logger.info(f"✅ Created new {table_name} structure with composite keys")
            
            # Create symbol metadata table for tracking latest keys
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbol_latest_keys (
                    symbol VARCHAR(20) PRIMARY KEY,
                    latest_daily_key INTEGER DEFAULT 0,
                    latest_weekly_key INTEGER DEFAULT 0,
                    latest_monthly_key INTEGER DEFAULT 0,
                    total_daily_candles INTEGER DEFAULT 0,
                    total_weekly_candles INTEGER DEFAULT 0,
                    total_monthly_candles INTEGER DEFAULT 0,
                    first_timestamp BIGINT,
                    latest_timestamp BIGINT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("✅ Created symbol_latest_keys metadata table")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"❌ Structure creation failed: {e}")
            raise

    async def migrate_existing_data(self):
        """Migrate existing data to new structure with composite keys"""
        logger.info("🔄 Migrating existing data to composite key system...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            timeframes = ['daily', 'weekly', 'monthly']
            
            for timeframe in timeframes:
                logger.info(f"🔄 Migrating {timeframe} candles...")
                
                # Get all symbols
                symbols = await conn.fetch(f"""
                    SELECT DISTINCT symbol 
                    FROM {timeframe}_candles_backup 
                    ORDER BY symbol
                """)
                
                symbol_count = 0
                total_candles_migrated = 0
                
                for symbol_row in symbols:
                    symbol = symbol_row['symbol']
                    symbol_count += 1
                    
                    # Get all candles for this symbol ordered by timestamp
                    candles = await conn.fetch(f"""
                        SELECT * FROM {timeframe}_candles_backup 
                        WHERE symbol = $1 
                        ORDER BY timestamp ASC
                    """, symbol)
                    
                    # Prepare migrated data with composite keys
                    migrated_data = []
                    
                    for idx, candle in enumerate(candles):
                        # Generate composite key: SYMBOL_SEQUENCE
                        composite_key = f"{symbol}_{idx}"
                        
                        # Collect all indicators into JSONB
                        indicators = {}
                        
                        # Static indicators
                        static_indicators = [
                            'rsi_14', 'sma_20', 'sma_50', 'ema_12', 'ema_26', 
                            'supertrend_10_2', 'supertrend_10_3', 
                            'supertrend_signal_10_2', 'supertrend_signal_10_3'
                        ]
                        
                        for indicator in static_indicators:
                            if candle[indicator] is not None:
                                indicators[indicator] = float(candle[indicator])
                        
                        # Add existing JSONB indicators
                        if candle['indicators']:
                            existing_indicators = candle['indicators'] if isinstance(candle['indicators'], dict) else json.loads(candle['indicators'])
                            indicators.update(existing_indicators)
                        
                        # Prepare row for new structure
                        migrated_data.append((
                            composite_key,                    # candle_key_id
                            symbol,                          # symbol
                            idx,                            # candle_sequence_number
                            candle['timestamp'],            # timestamp
                            candle['datetime'],             # datetime
                            float(candle['open']),          # open
                            float(candle['high']),          # high
                            float(candle['low']),           # low
                            float(candle['close']),         # close
                            int(candle['volume']),          # volume
                            json.dumps(indicators),         # indicators (JSONB)
                            candle['created_at'],           # created_at
                            candle['updated_at']            # updated_at
                        ))
                    
                    # Insert migrated data
                    if migrated_data:
                        await conn.executemany(f"""
                            INSERT INTO {timeframe}_candles_new (
                                candle_key_id, symbol, candle_sequence_number, 
                                timestamp, datetime, open, high, low, close, volume,
                                indicators, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        """, migrated_data)
                        
                        total_candles_migrated += len(migrated_data)
                        
                        # Update symbol metadata
                        first_timestamp = candles[0]['timestamp'] if candles else None
                        latest_timestamp = candles[-1]['timestamp'] if candles else None
                        latest_key = len(candles) - 1 if candles else 0
                        
                        await conn.execute(f"""
                            INSERT INTO symbol_latest_keys (
                                symbol, latest_{timeframe}_key, total_{timeframe}_candles,
                                first_timestamp, latest_timestamp
                            ) VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (symbol) DO UPDATE SET
                                latest_{timeframe}_key = EXCLUDED.latest_{timeframe}_key,
                                total_{timeframe}_candles = EXCLUDED.total_{timeframe}_candles,
                                first_timestamp = COALESCE(symbol_latest_keys.first_timestamp, EXCLUDED.first_timestamp),
                                latest_timestamp = GREATEST(symbol_latest_keys.latest_timestamp, EXCLUDED.latest_timestamp),
                                last_updated = CURRENT_TIMESTAMP
                        """, symbol, latest_key, len(candles), first_timestamp, latest_timestamp)
                    
                    if symbol_count % 50 == 0:
                        logger.info(f"   📊 Processed {symbol_count} symbols, {total_candles_migrated} total candles")
                
                logger.info(f"✅ Migrated {total_candles_migrated} {timeframe} candles from {symbol_count} symbols")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"❌ Data migration failed: {e}")
            raise

    async def create_optimized_indexes(self):
        """Create optimized indexes for the new structure"""
        logger.info("📊 Creating optimized indexes...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            timeframes = ['daily', 'weekly', 'monthly']
            
            for timeframe in timeframes:
                table_name = f"{timeframe}_candles_new"
                
                # Index for symbol + sequence queries
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_sequence 
                    ON {table_name}(symbol, candle_sequence_number DESC)
                """)
                
                # Index for timestamp queries (backward compatibility)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_timestamp 
                    ON {table_name}(timestamp DESC)
                """)
                
                # Index for datetime queries
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_datetime 
                    ON {table_name}(datetime DESC)
                """)
                
                # GIN index for JSONB indicators (fast indicator queries)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_indicators 
                    ON {table_name} USING GIN (indicators)
                """)
                
                # Composite index for symbol + timestamp (common query pattern)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_timestamp 
                    ON {table_name}(symbol, timestamp DESC)
                """)
                
                logger.info(f"✅ Created indexes for {table_name}")
            
            # Index for symbol metadata
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_latest_updated 
                ON symbol_latest_keys(last_updated DESC)
            """)
            
            logger.info("✅ All indexes created successfully")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"❌ Index creation failed: {e}")
            raise

    async def finalize_migration(self):
        """Finalize migration by replacing old tables with new ones"""
        logger.info("🔄 Finalizing migration - switching to new tables...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            timeframes = ['daily', 'weekly', 'monthly']
            
            for timeframe in timeframes:
                table_name = f"{timeframe}_candles"
                
                # Rename tables
                await conn.execute(f"DROP TABLE IF EXISTS {table_name}_old")
                await conn.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")
                await conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
                
                logger.info(f"✅ Switched to new {table_name}")
            
            await conn.close()
            
            logger.info("🎉 Migration finalized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Migration finalization failed: {e}")
            raise

    async def validate_migration(self):
        """Validate that migration was successful"""
        logger.info("🔍 Validating migration...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            # Check new table structure
            for timeframe in ['daily', 'weekly', 'monthly']:
                table_name = f"{timeframe}_candles_new"
                
                # Count records
                new_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                old_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name.replace('_new', '_backup')}")
                
                logger.info(f"✅ {table_name}: {new_count} records (original: {old_count})")
                
                if new_count != old_count:
                    logger.warning(f"⚠️ Record count mismatch for {table_name}")
                
                # Check composite keys
                sample = await conn.fetchrow(f"SELECT candle_key_id, symbol, candle_sequence_number FROM {table_name} LIMIT 1")
                if sample:
                    logger.info(f"✅ Sample composite key: {sample['candle_key_id']} (symbol: {sample['symbol']}, seq: {sample['candle_sequence_number']})")
            
            # Check symbol metadata
            symbol_count = await conn.fetchval("SELECT COUNT(*) FROM symbol_latest_keys")
            logger.info(f"✅ Symbol metadata: {symbol_count} symbols tracked")
            
            # Test composite key lookup
            test_key = await conn.fetchrow("SELECT candle_key_id FROM daily_candles_new LIMIT 1")
            if test_key:
                lookup_test = await conn.fetchrow("SELECT * FROM daily_candles_new WHERE candle_key_id = $1", test_key['candle_key_id'])
                if lookup_test:
                    logger.info("✅ Composite key lookup test: PASSED")
                else:
                    logger.error("❌ Composite key lookup test: FAILED")
            
            await conn.close()
            
            logger.info("✅ Migration validation completed")
            
        except Exception as e:
            logger.error(f"❌ Migration validation failed: {e}")
            raise

    async def rollback_migration(self):
        """Rollback migration if something goes wrong"""
        logger.info("🔄 Rolling back migration...")
        
        try:
            conn = await asyncpg.connect(database=self.target_database, **self.db_config)
            
            # Restore from backup
            for timeframe in ['daily', 'weekly', 'monthly']:
                table_name = f"{timeframe}_candles"
                
                await conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                await conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {table_name}_backup")
                
                logger.info(f"✅ Restored {table_name} from backup")
            
            await conn.close()
            
            logger.info("✅ Migration rolled back successfully")
            
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            raise

# Standalone migration script
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    migrator = DatabaseMigrator()
    
    try:
        await migrator.run_full_migration()
        await migrator.finalize_migration()
        
        print("\n" + "="*80)
        print("🎉 DATABASE MIGRATION COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("✅ Old structure: (symbol, timestamp) primary key")
        print("✅ New structure: candle_key_id primary key (20MICRONS_1, 20MICRONS_2)")
        print("✅ Symbol metadata table created for latest key tracking")
        print("✅ All indicators moved to optimized JSONB column")
        print("✅ Optimized indexes created for fast queries")
        print("="*80)
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        
        # Ask user if they want to rollback
        response = input("Do you want to rollback the migration? (y/N): ")
        if response.lower() == 'y':
            await migrator.rollback_migration()

if __name__ == "__main__":
    asyncio.run(main())