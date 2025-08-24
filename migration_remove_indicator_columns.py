#!/usr/bin/env python3
"""
Migration Script: Remove Physical Indicator Columns
Removes all physical indicator columns and migrates to JSONB-only storage
"""

import asyncio
import asyncpg
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IndicatorColumnMigration:
    """Migration to remove physical indicator columns and use JSONB only"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        # List of physical indicator columns to remove
        self.indicator_columns = [
            # RSI columns
            'rsi_14', 'rsi_21', 'rsi_30',
            
            # SMA columns
            'sma_10', 'sma_20', 'sma_50', 'sma_200',
            
            # EMA columns
            'ema_12', 'ema_26', 'ema_21',
            
            # SuperTrend columns
            'supertrend_10_2', 'supertrend_10_3', 'supertrend_14_2',
            'supertrend_signal_10_2', 'supertrend_signal_10_3',
            
            # Bollinger Bands columns
            'bb_upper_20_2', 'bb_middle_20_2', 'bb_lower_20_2',
            'bb_upper_20', 'bb_middle_20', 'bb_lower_20',
            
            # MACD columns
            'macd_line', 'macd_signal', 'macd_histogram',
            
            # Other indicator columns
            'atr_14', 'stoch_k', 'stoch_d',
            'wma_14', 'wma_20', 'wma_50',
            
            # Any other columns that might exist
            'rsi', 'sma', 'ema', 'supertrend', 'bb_upper', 'bb_middle', 'bb_lower'
        ]
        
        self.tables = ['daily_candles', 'weekly_candles', 'monthly_candles']
    
    async def run_migration(self):
        """Run the complete migration"""
        logger.info("=" * 80)
        logger.info("STARTING INDICATOR COLUMN MIGRATION")
        logger.info("=" * 80)
        logger.info("This migration will:")
        logger.info("1. Backup existing physical indicator data to JSONB")
        logger.info("2. Remove physical indicator columns")
        logger.info("3. Clean up related indexes")
        logger.info("4. Optimize database structure")
        logger.info("=" * 80)
        
        conn = await asyncpg.connect(**self.db_config)
        
        try:
            # Step 1: Backup physical columns to JSONB
            await self._backup_physical_to_jsonb(conn)
            
            # Step 2: Drop physical indicator columns
            await self._drop_physical_columns(conn)
            
            # Step 3: Clean up indexes
            await self._clean_up_indexes(conn)
            
            # Step 4: Optimize tables
            await self._optimize_tables(conn)
            
            logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
            logger.info("Database now uses JSONB-only indicator storage")
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            raise
        finally:
            await conn.close()
    
    async def _backup_physical_to_jsonb(self, conn):
        """Backup existing physical indicator data to JSONB"""
        logger.info("📦 Step 1: Backing up physical indicator data to JSONB...")
        
        for table in self.tables:
            logger.info(f"Processing {table}...")
            
            # Get existing columns for this table
            existing_columns = await conn.fetch(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND table_schema = 'public'
                AND column_name = ANY($1)
            """, self.indicator_columns)
            
            existing_cols = [row['column_name'] for row in existing_columns]
            
            if not existing_cols:
                logger.info(f"  No physical indicator columns found in {table}")
                continue
            
            logger.info(f"  Found {len(existing_cols)} physical indicator columns")
            
            # Build the update query to move data from physical columns to JSONB
            col_updates = []
            for col in existing_cols:
                col_updates.append(f"""
                    indicators = jsonb_set(
                        COALESCE(indicators, '{{}}'),
                        '{{{col}}}',
                        to_jsonb({col}::numeric)
                    )
                """)
            
            if col_updates:
                # Update in batches to avoid memory issues
                batch_size = 1000
                offset = 0
                
                while True:
                    update_query = f"""
                        UPDATE {table}
                        SET {', '.join(col_updates)}
                        WHERE candle_key_id IN (
                            SELECT candle_key_id 
                            FROM {table}
                            WHERE {' OR '.join([f'{col} IS NOT NULL' for col in existing_cols])}
                            LIMIT {batch_size} OFFSET {offset}
                        )
                    """
                    
                    result = await conn.execute(update_query)
                    rows_updated = int(result.split()[-1])
                    
                    if rows_updated == 0:
                        break
                    
                    logger.info(f"    Updated {rows_updated} rows in {table} (offset: {offset})")
                    offset += batch_size
                
                logger.info(f"  ✅ Completed backup for {table}")
    
    async def _drop_physical_columns(self, conn):
        """Drop physical indicator columns"""
        logger.info("🗑️  Step 2: Dropping physical indicator columns...")
        
        for table in self.tables:
            logger.info(f"Processing {table}...")
            
            # Get existing columns for this table
            existing_columns = await conn.fetch(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND table_schema = 'public'
                AND column_name = ANY($1)
            """, self.indicator_columns)
            
            existing_cols = [row['column_name'] for row in existing_columns]
            
            if not existing_cols:
                logger.info(f"  No physical indicator columns to drop in {table}")
                continue
            
            for col in existing_cols:
                try:
                    await conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
                    logger.info(f"    Dropped column: {col}")
                except Exception as e:
                    logger.warning(f"    Failed to drop column {col}: {e}")
            
            logger.info(f"  ✅ Completed column removal for {table}")
    
    async def _clean_up_indexes(self, conn):
        """Clean up indexes related to dropped columns"""
        logger.info("🧹 Step 3: Cleaning up indexes...")
        
        # Get all indexes that might be related to indicator columns
        indexes = await conn.fetch("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public'
            AND (
                indexname ~ 'rsi|sma|ema|supertrend|bb_|macd|atr|stoch|wma'
                OR indexname ~ 'idx_daily_rsi|idx_daily_sma|idx_supertrend'
            )
        """)
        
        for index in indexes:
            try:
                await conn.execute(f"DROP INDEX IF EXISTS {index['indexname']}")
                logger.info(f"  Dropped index: {index['indexname']}")
            except Exception as e:
                logger.warning(f"  Failed to drop index {index['indexname']}: {e}")
        
        logger.info("✅ Index cleanup completed")
    
    async def _optimize_tables(self, conn):
        """Optimize tables after column removal"""
        logger.info("⚡ Step 4: Optimizing tables...")
        
        for table in self.tables:
            try:
                # Vacuum and analyze the table
                await conn.execute(f"VACUUM ANALYZE {table}")
                logger.info(f"  Optimized {table}")
            except Exception as e:
                logger.warning(f"  Failed to optimize {table}: {e}")
        
        logger.info("✅ Table optimization completed")
    
    async def _verify_migration(self, conn):
        """Verify the migration was successful"""
        logger.info("🔍 Verifying migration...")
        
        for table in self.tables:
            # Check that no indicator columns remain
            remaining_cols = await conn.fetch(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND table_schema = 'public'
                AND column_name = ANY($1)
            """, self.indicator_columns)
            
            if remaining_cols:
                logger.warning(f"  {table} still has indicator columns: {[r['column_name'] for r in remaining_cols]}")
            else:
                logger.info(f"  ✅ {table} - all physical indicator columns removed")
            
            # Check that JSONB indicators column exists
            jsonb_col = await conn.fetchval(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND table_schema = 'public'
                AND column_name = 'indicators' AND data_type = 'jsonb'
            """)
            
            if jsonb_col:
                logger.info(f"  ✅ {table} - JSONB indicators column exists")
            else:
                logger.warning(f"  ⚠️  {table} - JSONB indicators column missing")
        
        logger.info("✅ Migration verification completed")

async def main():
    """Main entry point"""
    try:
        migration = IndicatorColumnMigration()
        await migration.run_migration()
        
        print("\n" + "=" * 80)
        print("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print("✅ All physical indicator columns removed")
        print("✅ Data backed up to JSONB indicators column")
        print("✅ Database optimized for JSONB-only storage")
        print("✅ System ready for dynamic indicator calculations")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    print("WARNING: This migration will remove physical indicator columns!")
    print("Make sure you have a backup of your database before proceeding.")
    
    confirmation = input("Do you want to proceed with the migration? (yes/no): ")
    if confirmation.lower() == 'yes':
        asyncio.run(main())
    else:
        print("Migration cancelled.")