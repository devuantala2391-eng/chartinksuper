#!/usr/bin/env python3
"""
Complete Database Migration Script
Handles all database structure issues automatically:
- Creates missing databases
- Creates missing tables 
- Adds missing columns
- Creates required indexes
- Migrates data if needed
- Fixes all "relation does not exist" errors
"""

import os
import sys
import asyncio
import asyncpg
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add python-api to path
sys.path.append(str(Path(__file__).parent.parent / "python-api"))

from services.ultra_fast_database_service import ultra_fast_db
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Complete database migration and structure management"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        self.required_tables = {
            'daily_candles': {
                'composite_key': {
                    'candle_key_id': 'VARCHAR(50) PRIMARY KEY',
                    'symbol': 'VARCHAR(20) NOT NULL',
                    'candle_sequence_number': 'INTEGER NOT NULL',
                    'timestamp': 'BIGINT NOT NULL',
                    'datetime': 'TIMESTAMP NOT NULL',
                    'open': 'DECIMAL(20,6) NOT NULL',
                    'high': 'DECIMAL(20,6) NOT NULL',
                    'low': 'DECIMAL(20,6) NOT NULL',
                    'close': 'DECIMAL(20,6) NOT NULL',
                    'volume': 'BIGINT NOT NULL',
                    'indicators': 'JSONB DEFAULT \'{}\'',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                },
            },
            'weekly_candles': {
                'composite_key': {
                    'candle_key_id': 'VARCHAR(50) PRIMARY KEY',
                    'symbol': 'VARCHAR(20) NOT NULL',
                    'candle_sequence_number': 'INTEGER NOT NULL',
                    'timestamp': 'BIGINT NOT NULL',
                    'datetime': 'TIMESTAMP NOT NULL',
                    'open': 'DECIMAL(20,6) NOT NULL',
                    'high': 'DECIMAL(20,6) NOT NULL',
                    'low': 'DECIMAL(20,6) NOT NULL',
                    'close': 'DECIMAL(20,6) NOT NULL',
                    'volume': 'BIGINT NOT NULL',
                    'indicators': 'JSONB DEFAULT \'{}\'',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
            },
            'monthly_candles': {
                'composite_key': {
                    'candle_key_id': 'VARCHAR(50) PRIMARY KEY',
                    'symbol': 'VARCHAR(20) NOT NULL',
                    'candle_sequence_number': 'INTEGER NOT NULL',
                    'timestamp': 'BIGINT NOT NULL',
                    'datetime': 'TIMESTAMP NOT NULL',
                    'open': 'DECIMAL(20,6) NOT NULL',
                    'high': 'DECIMAL(20,6) NOT NULL',
                    'low': 'DECIMAL(20,6) NOT NULL',
                    'close': 'DECIMAL(20,6) NOT NULL',
                    'volume': 'BIGINT NOT NULL',
                    'indicators': 'JSONB DEFAULT \'{}\'',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
            },
            'symbol_latest_keys': {
                'structure': {
                    'symbol': 'VARCHAR(20) PRIMARY KEY',
                    'latest_daily_key': 'INTEGER DEFAULT -1',
                    'latest_weekly_key': 'INTEGER DEFAULT -1',
                    'latest_monthly_key': 'INTEGER DEFAULT -1',
                    'total_daily_candles': 'INTEGER DEFAULT 0',
                    'total_weekly_candles': 'INTEGER DEFAULT 0',
                    'total_monthly_candles': 'INTEGER DEFAULT 0',
                    'first_timestamp': 'BIGINT',
                    'latest_timestamp': 'BIGINT',
                    'last_updated': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
            }
        }
    
    async def run_complete_migration(self):
        """Run complete database migration and structure fixes"""
        
        print("STARTING COMPLETE DATABASE MIGRATION")
        print("=" * 60)
        print("This will:")
        print("1. Create database if missing")
        print("2. Create all required tables")
        print("3. Add missing columns")
        print("4. Create performance indexes")
        print("5. Fix all 'relation does not exist' errors")
        print("=" * 60)
        
        try:
            # Step 1: Ensure database exists
            await self._ensure_database_exists()
            
            # Step 2: Connect to target database
            conn = await asyncpg.connect(**self.db_config)
            
            # Step 3: Analyze current structure
            current_structure = await self._analyze_current_structure(conn)
            
            # Step 4: Create missing tables
            await self._create_missing_tables(conn, current_structure)
            
            # Step 5: Add missing columns
            await self._add_missing_columns(conn, current_structure)
            
            # Step 6: Create indexes
            await self._create_performance_indexes(conn)
            
            # Step 7: Validate final structure
            await self._validate_final_structure(conn)
            
            await conn.close()
            
            print("\nMIGRATION COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            print("All database structure issues have been resolved.")
            print("The system should now work without 'relation does not exist' errors.")
            print("You can now run the hard-refresh API safely.")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
    
    async def _ensure_database_exists(self):
        """Create database if it doesn't exist"""
        print("Step 1: Ensuring database exists...")
        
        try:
            # Connect to postgres database
            conn = await asyncpg.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database='postgres',
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            
            # Check if target database exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                self.db_config['database']
            )
            
            if not exists:
                await conn.execute(f"CREATE DATABASE {self.db_config['database']}")
                print(f"   Created database: {self.db_config['database']}")
            else:
                print(f"   Database exists: {self.db_config['database']}")
            
            await conn.close()
            
        except Exception as e:
            logger.error(f"Failed to ensure database exists: {e}")
            raise
    
    async def _analyze_current_structure(self, conn):
        """Analyze current database structure"""
        print("Step 2: Analyzing current database structure...")
        
        structure = {}
        
        # Get all tables
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """)
        
        table_names = [t['tablename'] for t in tables]
        print(f"   Found tables: {table_names}")
        
        # Analyze each table
        for table_name in table_names:
            if table_name in self.required_tables:
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = $1
                    ORDER BY ordinal_position
                """, table_name)
                
                structure[table_name] = {
                    'columns': {col['column_name']: {
                        'type': col['data_type'],
                        'nullable': col['is_nullable'],
                        'default': col['column_default']
                    } for col in columns}
                }
                
                # Get primary key
                pk = await conn.fetch("""
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = $1::regclass AND i.indisprimary
                """, table_name)
                
                structure[table_name]['primary_key'] = [p['attname'] for p in pk]
                
                print(f"   {table_name}: {len(structure[table_name]['columns'])} columns, PK: {structure[table_name]['primary_key']}")
        
        return structure
    
    async def _create_missing_tables(self, conn, current_structure):
        """Create any missing required tables"""
        print("Step 3: Creating missing tables...")
        
        for table_name, table_def in self.required_tables.items():
            if table_name not in current_structure:
                print(f"   Creating missing table: {table_name}")
                
                # Determine which structure to use
                if table_name == 'daily_candles':
                    # For daily_candles, create with composite key structure for ultra-fast processing
                    columns_def = table_def['composite_key']
                    primary_key = ''  # Primary key already defined in column
                elif table_name == 'symbol_latest_keys':
                    columns_def = table_def['structure']
                    primary_key = ''  # Primary key already defined in column
                else:
                    # For weekly/monthly, use composite key structure
                    columns_def = table_def['composite_key']
                    primary_key = ''  # Primary key already defined in column
                
                # Build CREATE TABLE statement
                column_defs = []
                for col_name, col_type in columns_def.items():
                    column_defs.append(f"{col_name} {col_type}")
                
                create_sql = f"CREATE TABLE {table_name} ({', '.join(column_defs)}"
                if primary_key:
                    create_sql += f", {primary_key}"
                create_sql += ")"
                
                await conn.execute(create_sql)
                print(f"   Created table: {table_name}")
            else:
                print(f"   Table exists: {table_name}")
    
    async def _add_missing_columns(self, conn, current_structure):
        """Add missing columns to existing tables"""
        print("Step 4: Adding missing columns...")
        
        for table_name, table_def in self.required_tables.items():
            if table_name in current_structure:
                current_columns = current_structure[table_name]['columns']
                
                # Determine required columns based on table
                if table_name == 'daily_candles':
                    required_columns = table_def['composite_key']
                elif table_name == 'symbol_latest_keys':
                    required_columns = table_def['structure']
                else:
                    required_columns = table_def['composite_key']
                
                # Check for missing columns
                missing_columns = []
                for col_name, col_type in required_columns.items():
                    if col_name not in current_columns:
                        missing_columns.append((col_name, col_type))
                
                if missing_columns:
                    print(f"   Adding {len(missing_columns)} missing columns to {table_name}:")
                    for col_name, col_type in missing_columns:
                        # Skip PRIMARY KEY constraint in ALTER TABLE
                        clean_col_type = col_type.replace(' PRIMARY KEY', '')
                        
                        try:
                            await conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {clean_col_type}")
                            print(f"     Added column: {col_name}")
                        except Exception as e:
                            if "already exists" in str(e):
                                print(f"     Column exists: {col_name}")
                            else:
                                logger.warning(f"Failed to add column {col_name}: {e}")
                else:
                    print(f"   All columns exist in {table_name}")
    
    async def _create_performance_indexes(self, conn):
        """Create performance indexes"""
        print("Step 5: Creating performance indexes...")
        
        indexes = [
            # Daily candles indexes
            ("idx_daily_symbol_timestamp", "daily_candles", "(symbol, timestamp DESC)"),
            ("idx_daily_timestamp", "daily_candles", "(timestamp DESC)"),
            ("idx_daily_symbol", "daily_candles", "(symbol)"),
            ("idx_daily_indicators", "daily_candles", "USING GIN (indicators)"),
            
            # Weekly candles indexes
            ("idx_weekly_symbol_timestamp", "weekly_candles", "(symbol, timestamp DESC)"),
            ("idx_weekly_timestamp", "weekly_candles", "(timestamp DESC)"),
            
            # Monthly candles indexes
            ("idx_monthly_symbol_timestamp", "monthly_candles", "(symbol, timestamp DESC)"),
            ("idx_monthly_timestamp", "monthly_candles", "(timestamp DESC)"),
            
            # Symbol metadata indexes
            ("idx_symbol_latest_keys_symbol", "symbol_latest_keys", "(symbol)"),
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                # Check if table exists first
                table_exists = await conn.fetchval("""
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = $1
                """, table_name)
                
                if table_exists:
                    await conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {columns}")
                    print(f"   Created index: {index_name}")
                else:
                    print(f"   Skipped index {index_name} (table {table_name} doesn't exist)")
            except Exception as e:
                logger.warning(f"Failed to create index {index_name}: {e}")
    
    async def _validate_final_structure(self, conn):
        """Validate final database structure"""
        print("Step 6: Validating final structure...")
        
        validation_results = []
        
        for table_name in self.required_tables:
            # Check if table exists
            exists = await conn.fetchval("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = $1
            """, table_name)
            
            if exists:
                # Count columns
                col_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = $1
                """, table_name)
                
                validation_results.append(f"   {table_name}: {col_count} columns")
            else:
                validation_results.append(f"   {table_name}: MISSING")
        
        for result in validation_results:
            print(result)
        
        # Test symbol_latest_keys specifically
        try:
            await conn.execute("SELECT symbol FROM symbol_latest_keys LIMIT 1")
            print("   symbol_latest_keys table is queryable")
        except Exception as e:
            print(f"   symbol_latest_keys query test failed: {e}")

async def main():
    """Run the complete migration"""
    migrator = DatabaseMigrator()
    await migrator.run_complete_migration()

if __name__ == "__main__":
    asyncio.run(main())