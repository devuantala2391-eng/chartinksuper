#!/usr/bin/env python3
"""
Fix Database Structure - Add Missing Columns
Adds the missing candle_sequence_number column and migrates to composite key structure
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

async def fix_database_structure():
    """Add missing candle_sequence_number column and migrate to composite key structure"""
    
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': 'nse_highspeed',
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', '123'),
    }
    
    conn = await asyncpg.connect(**db_config)
    
    try:
        logger.info("=" * 80)
        logger.info("FIXING DATABASE STRUCTURE - ADDING MISSING COLUMNS")
        logger.info("=" * 80)
        
        tables = ['daily_candles', 'weekly_candles', 'monthly_candles']
        
        for table in tables:
            logger.info(f"\n📊 Processing table: {table}")
            
            # Check if table exists
            table_exists = await conn.fetchval(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = '{table}'
                )
            """)
            
            if not table_exists:
                logger.info(f"  Table {table} doesn't exist, creating it...")
                await create_table_with_proper_structure(conn, table)
                continue
            
            # Check current columns
            columns = await conn.fetch(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)
            
            column_names = [col['column_name'] for col in columns]
            logger.info(f"  Current columns: {column_names}")
            
            # Check what needs to be added
            needs_candle_key_id = 'candle_key_id' not in column_names
            needs_sequence_number = 'candle_sequence_number' not in column_names
            needs_indicators_column = 'indicators' not in column_names
            
            # Add missing columns
            if needs_candle_key_id:
                logger.info("  ➕ Adding candle_key_id column...")
                await conn.execute(f"""
                    ALTER TABLE {table} 
                    ADD COLUMN candle_key_id VARCHAR(50)
                """)
            
            if needs_sequence_number:
                logger.info("  ➕ Adding candle_sequence_number column...")
                await conn.execute(f"""
                    ALTER TABLE {table} 
                    ADD COLUMN candle_sequence_number INTEGER
                """)
            
            if needs_indicators_column:
                logger.info("  ➕ Adding indicators JSONB column...")
                await conn.execute(f"""
                    ALTER TABLE {table} 
                    ADD COLUMN indicators JSONB DEFAULT '{{}}'
                """)
            
            # Populate candle_key_id and sequence number if they were just added
            if needs_candle_key_id or needs_sequence_number:
                logger.info("  🔄 Populating composite key data...")
                
                # Get all records ordered by timestamp
                records = await conn.fetch(f"""
                    SELECT symbol, timestamp, 
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp) - 1 as seq_num
                    FROM {table}
                    ORDER BY symbol, timestamp
                """)
                
                # Update in batches
                batch_size = 1000
                for i in range(0, len(records), batch_size):
                    batch = records[i:i + batch_size]
                    
                    for record in batch:
                        symbol = record['symbol']
                        timestamp = record['timestamp']
                        seq_num = record['seq_num']
                        candle_key_id = f"{symbol}_{seq_num}"
                        
                        if needs_candle_key_id:
                            await conn.execute(f"""
                                UPDATE {table} 
                                SET candle_key_id = $1 
                                WHERE symbol = $2 AND timestamp = $3
                            """, candle_key_id, symbol, timestamp)
                        
                        if needs_sequence_number:
                            await conn.execute(f"""
                                UPDATE {table} 
                                SET candle_sequence_number = $1 
                                WHERE symbol = $2 AND timestamp = $3
                            """, seq_num, symbol, timestamp)
                    
                    logger.info(f"    Updated batch {i//batch_size + 1}/{(len(records) + batch_size - 1)//batch_size}")
            
            # Make columns NOT NULL if they were just added
            if needs_candle_key_id:
                logger.info("  🔒 Making candle_key_id NOT NULL...")
                await conn.execute(f"""
                    ALTER TABLE {table} 
                    ALTER COLUMN candle_key_id SET NOT NULL
                """)
            
            if needs_sequence_number:
                logger.info("  🔒 Making candle_sequence_number NOT NULL...")
                await conn.execute(f"""
                    ALTER TABLE {table} 
                    ALTER COLUMN candle_sequence_number SET NOT NULL
                """)
            
            # Create composite primary key if needed
            current_pk = await conn.fetch(f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = '{table}'::regclass AND i.indisprimary
            """)
            
            current_pk_columns = [pk['attname'] for pk in current_pk]
            
            if 'candle_key_id' not in current_pk_columns:
                logger.info("  🔑 Updating primary key to candle_key_id...")
                
                # Drop existing primary key if it exists
                if current_pk_columns:
                    await conn.execute(f"""
                        ALTER TABLE {table} DROP CONSTRAINT {table}_pkey
                    """)
                
                # Add new primary key
                await conn.execute(f"""
                    ALTER TABLE {table} ADD PRIMARY KEY (candle_key_id)
                """)
            
            logger.info(f"  ✅ Completed migration for {table}")
        
        logger.info("\n🔍 Creating optimized indexes...")
        
        # Create indexes for tables that now have the proper structure
        for table in tables:
            # Check if candle_sequence_number exists
            has_sequence = await conn.fetchval(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = '{table}' AND column_name = 'candle_sequence_number'
                )
            """)
            
            if has_sequence:
                timeframe = table.replace('_candles', '')
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_symbol_key 
                    ON {table}(symbol, candle_sequence_number DESC)
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_timestamp 
                    ON {table}(timestamp DESC)
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{timeframe}_indicators 
                    ON {table} USING GIN (indicators)
                """)
                
                logger.info(f"  ✅ Created indexes for {table}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ DATABASE STRUCTURE FIXED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info("✅ All tables now have:")
        logger.info("   - candle_key_id (PRIMARY KEY)")
        logger.info("   - candle_sequence_number (NOT NULL)")
        logger.info("   - indicators (JSONB)")
        logger.info("   - Optimized indexes")
        logger.info("✅ System is ready for ultra-fast database operations!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()

async def create_table_with_proper_structure(conn, table_name):
    """Create a table with the proper composite key structure"""
    await conn.execute(f"""
        CREATE TABLE {table_name} (
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
            indicators JSONB DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.info(f"  ✅ Created {table_name} with proper structure")

if __name__ == "__main__":
    print("This script will fix the database structure by adding missing columns.")
    print("It's safe to run multiple times and will not damage existing data.")
    
    confirmation = input("Do you want to proceed? (yes/no): ")
    if confirmation.lower() == 'yes':
        asyncio.run(fix_database_structure())
    else:
        print("Operation cancelled.")