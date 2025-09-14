"""
Database Migration Service
Ensures all required stored procedures are available in the database
"""
import asyncio
import asyncpg
import logging
import os
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

class DatabaseMigrationService:
    """
    Service to handle database migrations, particularly stored procedures
    """
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': 'nse_highspeed',
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', '123'),
        }
        
        # Required stored procedures for weekly candle generation and percentage calculations
        self.required_procedures = [
            'generate_weekly_candles_for_symbol',
            'process_symbol_weekly_only',
            'process_all_symbols_weekly_only',
            'calculate_all_indicators_for_symbol',
            'process_symbol_comprehensive',
            'calculate_monthly_percentage_change',  # Added for monthly percentage
            'calculate_monthly_percentage_change_for_symbol',  # Added for monthly percentage
            'calculate_percentage_change',  # Added for general percentage
            'calculate_weekly_percentage_change',  # Added for weekly percentage
            'calculate_weekly_percentage_change_for_symbol',  # Added for weekly percentage
            'calculate_atr',  # Added for ATR calculation
            'calculate_weekly_atr',  # Added for weekly ATR
            'calculate_monthly_atr'  # Added for monthly ATR
        ]
    
    async def check_and_apply_migrations(self) -> Dict[str, any]:
        """
        Check if required stored procedures exist and apply migrations if needed
        """
        try:
            conn = await asyncpg.connect(**self.db_config)
            
            # Check which procedures exist
            existing_procedures = await self._get_existing_procedures(conn)
            missing_procedures = set(self.required_procedures) - set(existing_procedures)
            
            if missing_procedures:
                logger.warning(f"Missing stored procedures: {missing_procedures}")
                logger.info("Applying database migrations...")
                
                migration_result = await self._apply_comprehensive_calculations_migration(conn)
                
                if migration_result['success']:
                    # Verify procedures were created
                    updated_procedures = await self._get_existing_procedures(conn)
                    still_missing = set(self.required_procedures) - set(updated_procedures)
                    
                    if still_missing:
                        logger.error(f"Migration completed but procedures still missing: {still_missing}")
                        result = {
                            'success': False,
                            'message': f'Migration incomplete - still missing: {still_missing}',
                            'applied': True,
                            'missing_before': list(missing_procedures),
                            'missing_after': list(still_missing)
                        }
                    else:
                        logger.info("✅ All stored procedures are now available")
                        result = {
                            'success': True,
                            'message': 'Database migration completed successfully',
                            'applied': True,
                            'procedures_created': list(missing_procedures),
                            'total_procedures': len(updated_procedures)
                        }
                else:
                    logger.error(f"Migration failed: {migration_result['error']}")
                    result = {
                        'success': False,
                        'message': f"Migration failed: {migration_result['error']}",
                        'applied': False,
                        'missing_procedures': list(missing_procedures)
                    }
            else:
                logger.info("✅ All required stored procedures are available")
                result = {
                    'success': True,
                    'message': 'All required stored procedures are available',
                    'applied': False,
                    'total_procedures': len(existing_procedures)
                }
            
            await conn.close()
            return result
            
        except Exception as e:
            logger.error(f"Migration check failed: {e}")
            return {
                'success': False,
                'message': f'Migration check failed: {str(e)}',
                'applied': False,
                'error': str(e)
            }
    
    async def _get_existing_procedures(self, conn) -> List[str]:
        """Get list of existing stored procedures"""
        procedures = await conn.fetch("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_type = 'FUNCTION'
        """)
        
        return [proc['routine_name'] for proc in procedures]
    
    async def _apply_comprehensive_calculations_migration(self, conn) -> Dict[str, any]:
        """Apply the comprehensive calculations SQL file and percentage calculations"""
        try:
            # List of SQL files to apply in order
            sql_files = [
                "comprehensive_calculations.sql",
                "calculate_monthly_percentage_change.sql",  # CORRECT monthly percentage implementation
                "calculate_percentage_change.sql",  # General percentage (now delegates monthly to correct implementation)
                "calculate_weekly_percentage_change.sql",  # Weekly percentage functions
                "calculate_atr.sql",  # ATR calculation with Wilder's smoothing and TradingView matching
                "calculate_supertrend.sql",  # CORRECTED SuperTrend with proper band persistence
                "fix_weekly_monthly_supertrend_properly.sql"  # Fixed weekly/monthly SuperTrend
            ]
            
            applied_files = []
            total_sql_size = 0
            
            for sql_filename in sql_files:
                # Find the SQL file
                sql_file_path = Path(__file__).parent.parent / "sql" / "stored_procedures" / sql_filename
                
                if not sql_file_path.exists():
                    logger.warning(f"SQL file not found, skipping: {sql_file_path}")
                    continue
                
                # Read and execute the SQL
                with open(sql_file_path, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                
                logger.info(f"Applying {sql_filename} migration ({len(sql_content)} chars)")
                
                # Execute the SQL (this creates all the functions)
                await conn.execute(sql_content)
                
                applied_files.append(sql_filename)
                total_sql_size += len(sql_content)
                logger.info(f"✅ {sql_filename} migration applied successfully")
            
            if not applied_files:
                return {
                    'success': False,
                    'error': 'No SQL files found to apply'
                }
            
            logger.info(f"✅ All migrations applied successfully: {', '.join(applied_files)}")
            
            return {
                'success': True,
                'sql_files': applied_files,
                'total_sql_size': total_sql_size
            }
            
        except Exception as e:
            logger.error(f"Failed to apply migration: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def verify_weekly_candle_generation(self, test_symbol: str = None) -> Dict[str, any]:
        """
        Verify that weekly candle generation works properly
        """
        try:
            conn = await asyncpg.connect(**self.db_config)
            
            # Get a symbol to test with if not provided
            if not test_symbol:
                test_symbol = await conn.fetchval("SELECT symbol FROM daily_candles LIMIT 1")
            
            if not test_symbol:
                return {
                    'success': False,
                    'message': 'No daily candles found to test with'
                }
            
            # Test the weekly candle generation procedure
            logger.info(f"Testing weekly candle generation with symbol: {test_symbol}")
            
            result = await conn.fetchrow("""
                SELECT * FROM process_symbol_weekly_only($1)
            """, test_symbol)
            
            await conn.close()
            
            if result and result['status'] == 'SUCCESS':
                logger.info(f"✅ Weekly candle generation test passed: {result['weekly_candles_generated']} candles generated")
                return {
                    'success': True,
                    'test_symbol': test_symbol,
                    'weekly_candles_generated': result['weekly_candles_generated'],
                    'daily_candles_updated': result['daily_candles_updated'],
                    'execution_time_ms': result['total_execution_time_ms']
                }
            else:
                error_msg = result['status'] if result else 'No result returned'
                logger.error(f"❌ Weekly candle generation test failed: {error_msg}")
                return {
                    'success': False,
                    'test_symbol': test_symbol,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Weekly candle generation verification failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

# Global instance
database_migration_service = DatabaseMigrationService()