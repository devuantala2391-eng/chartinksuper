"""
PostgreSQL Stored Procedure Indicator Service
Manages indicator calculations using PostgreSQL stored procedures for high performance
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from services.ultra_fast_database_service import ultra_fast_db

logger = logging.getLogger(__name__)

class PostgresIndicatorService:
    """Service for managing indicator calculations via PostgreSQL stored procedures"""
    
    def __init__(self):
        self.procedures_installed = set()
    
    async def initialize(self):
        """Initialize the service and install required stored procedures"""
        try:
            # Ensure database is initialized
            await ultra_fast_db.initialize()
            
            # Install stored procedures
            await self._install_percentage_change_procedures()
            
            logger.info("✅ PostgresIndicatorService initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgresIndicatorService: {e}")
            return False
    
    async def _install_percentage_change_procedures(self):
        """Install percentage change calculation stored procedures (daily, weekly, and monthly)"""
        try:
            # Install daily percentage change procedures
            daily_sql_path = Path(__file__).parent.parent / "sql" / "stored_procedures" / "calculate_percentage_change.sql"
            
            if not daily_sql_path.exists():
                raise FileNotFoundError(f"Daily procedure file not found: {daily_sql_path}")
            
            # Install weekly percentage change procedures
            weekly_sql_path = Path(__file__).parent.parent / "sql" / "stored_procedures" / "calculate_weekly_percentage_change.sql"
            
            if not weekly_sql_path.exists():
                raise FileNotFoundError(f"Weekly procedure file not found: {weekly_sql_path}")
            
            # Install monthly percentage change procedures
            monthly_sql_path = Path(__file__).parent.parent / "sql" / "stored_procedures" / "calculate_monthly_percentage_change.sql"
            
            if not monthly_sql_path.exists():
                raise FileNotFoundError(f"Monthly procedure file not found: {monthly_sql_path}")
            
            
            
            async with ultra_fast_db.pool.acquire() as conn:
                # First, drop any existing conflicting functions to prevent signature conflicts
                conflicting_functions = [
                    "calculate_daily_percentage_change",
                    "calculate_weekly_percentage_change", 
                    "calculate_monthly_percentage_change",
                    "calculate_weekly_percentage_change_for_symbol",
                    "calculate_monthly_percentage_change_for_symbol",
                    "install_percentage_change_procedures",
                    "batch_calculate_daily_percentage",
                    "batch_calculate_weekly_percentage",
                    "batch_calculate_monthly_percentage"
                ]
                
                for func_name in conflicting_functions:
                    try:
                        await conn.execute(f"DROP FUNCTION IF EXISTS {func_name} CASCADE")
                        logger.debug(f"Dropped conflicting function: {func_name}")
                    except Exception:
                        pass  # Ignore errors if function doesn't exist
                
                # Install daily procedures
                with open(daily_sql_path, 'r', encoding='utf-8') as f:
                    daily_sql_content = f.read()
                await conn.execute(daily_sql_content)
                
                # Install weekly procedures
                with open(weekly_sql_path, 'r', encoding='utf-8') as f:
                    weekly_sql_content = f.read()
                await conn.execute(weekly_sql_content)
                
                # Install monthly procedures
                with open(monthly_sql_path, 'r', encoding='utf-8') as f:
                    monthly_sql_content = f.read()
                await conn.execute(monthly_sql_content)
                
                
            
            self.procedures_installed.add('calculate_percentage_change')
            self.procedures_installed.add('calculate_weekly_percentage_change')
            self.procedures_installed.add('calculate_monthly_percentage_change')
            logger.info("✅ Installed daily, weekly, and monthly percentage change stored procedures")
            
        except Exception as e:
            logger.error(f"Failed to install percentage change procedures: {e}")
            raise
    
    async def calculate_percentage_change(
        self, 
        timeframe: str = 'daily',
        symbol: Optional[str] = None,
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Calculate percentage change using PostgreSQL stored procedure
        
        Args:
            timeframe: 'daily', 'weekly', or 'monthly'
            symbol: Optional symbol filter (None for all symbols)
            batch_size: Processing batch size
            
        Returns:
            Dict with calculation results
        """
        start_time = time.time()
        
        try:
            if 'calculate_percentage_change' not in self.procedures_installed:
                await self._install_percentage_change_procedures()
            
            logger.info(f"🚀 Starting {timeframe} percentage change calculation via PostgreSQL")
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Route to appropriate stored procedure based on timeframe
                if timeframe == 'weekly':
                    # Use weekly percentage change stored procedure
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_weekly_percentage_change($1, $2)",
                        symbol, batch_size
                    )
                elif timeframe == 'monthly':
                    # Use monthly percentage change stored procedure
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_monthly_percentage_change($1, $2)",
                        symbol, batch_size
                    )
                else:
                    # Use daily percentage change stored procedure for daily
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_percentage_change($1, $2, $3)",
                        timeframe, symbol, batch_size
                    )
                
                processing_time = time.time() - start_time
                
                success = result['status'] == 'SUCCESS'
                
                if success:
                    logger.info(f"✅ {timeframe.title()} percentage change calculation completed:")
                    logger.info(f"   📊 Processed symbols: {result['processed_symbols']}")
                    logger.info(f"   🔄 Updated rows: {result['updated_rows']}")
                    logger.info(f"   ⏱️ DB execution time: {result['execution_time_ms']}ms")
                    logger.info(f"   🎯 Total time: {processing_time:.2f}s")
                else:
                    logger.error(f"❌ {timeframe} percentage change calculation failed: {result['status']}")
                
                return {
                    "success": success,
                    "timeframe": timeframe,
                    "processed_symbols": result['processed_symbols'],
                    "updated_rows": result['updated_rows'],
                    "db_execution_time_ms": result['execution_time_ms'],
                    "total_time_seconds": processing_time,
                    "status": result['status']
                }
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ PostgreSQL percentage change calculation failed: {e}")
            
            return {
                "success": False,
                "timeframe": timeframe,
                "processed_symbols": 0,
                "updated_rows": 0,
                "db_execution_time_ms": 0,
                "total_time_seconds": processing_time,
                "status": f"ERROR: {str(e)}"
            }
    
    async def calculate_percentage_change_for_symbol(
        self, 
        symbol: str,
        timeframe: str = 'daily'
    ) -> Dict[str, Any]:
        """
        Calculate percentage change for a specific symbol
        
        Args:
            symbol: Stock symbol
            timeframe: 'daily', 'weekly', or 'monthly'
            
        Returns:
            Dict with calculation results
        """
        start_time = time.time()
        
        try:
            logger.info(f"🎯 Calculating {timeframe} percentage change for {symbol}")
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Route to appropriate stored procedure based on timeframe
                if timeframe == 'weekly':
                    # Use weekly percentage change stored procedure
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_weekly_percentage_change_for_symbol($1)",
                        symbol
                    )
                elif timeframe == 'monthly':
                    # Use monthly percentage change stored procedure
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_monthly_percentage_change_for_symbol($1)",
                        symbol
                    )
                else:
                    # Use daily percentage change stored procedure for daily
                    result = await conn.fetchrow(
                        "SELECT * FROM calculate_percentage_change_for_symbol($1, $2)",
                        symbol, timeframe
                    )
                
                processing_time = time.time() - start_time
                success = result['status'] == 'SUCCESS'
                
                if success:
                    logger.info(f"✅ {symbol} {timeframe} percentage change: {result['updated_rows']} rows updated")
                else:
                    logger.error(f"❌ {symbol} {timeframe} percentage change failed: {result['status']}")
                
                return {
                    "success": success,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "updated_rows": result['updated_rows'],
                    "total_time_seconds": processing_time,
                    "status": result['status']
                }
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ {symbol} {timeframe} percentage change calculation failed: {e}")
            
            return {
                "success": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "updated_rows": 0,
                "total_time_seconds": processing_time,
                "status": f"ERROR: {str(e)}"
            }
    
    async def check_percentage_change_coverage(
        self, 
        timeframe: str = 'daily'
    ) -> Dict[str, Any]:
        """
        Check percentage change indicator coverage
        
        Args:
            timeframe: 'daily', 'weekly', or 'monthly'
            
        Returns:
            Dict with coverage statistics
        """
        try:
            async with ultra_fast_db.pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT * FROM check_percentage_change_coverage($1)",
                    timeframe
                )
                
                return {
                    "timeframe": timeframe,
                    "total_rows": result['total_rows'],
                    "rows_with_indicator": result['rows_with_indicator'],
                    "coverage_percentage": float(result['coverage_percentage']),
                    "missing_rows": result['missing_rows']
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to check {timeframe} percentage change coverage: {e}")
            return {
                "timeframe": timeframe,
                "total_rows": 0,
                "rows_with_indicator": 0,
                "coverage_percentage": 0.0,
                "missing_rows": 0,
                "error": str(e)
            }
    
    async def is_calculation_needed(
        self, 
        timeframe: str = 'daily',
        threshold_percentage: float = 95.0
    ) -> bool:
        """
        Check if percentage change calculation is needed based on coverage threshold
        
        Args:
            timeframe: 'daily', 'weekly', or 'monthly'
            threshold_percentage: Minimum coverage percentage to skip calculation
            
        Returns:
            True if calculation is needed, False otherwise
        """
        try:
            coverage = await self.check_percentage_change_coverage(timeframe)
            
            if 'error' in coverage:
                logger.warning(f"Unable to check coverage for {timeframe}, assuming calculation needed")
                return True
            
            current_coverage = coverage['coverage_percentage']
            needed = current_coverage < threshold_percentage
            
            if needed:
                logger.info(f"{timeframe.title()} percentage change calculation needed: {current_coverage:.1f}% < {threshold_percentage}%")
            else:
                logger.info(f"{timeframe.title()} percentage change calculation not needed: {current_coverage:.1f}% >= {threshold_percentage}%")
            
            return needed
            
        except Exception as e:
            logger.error(f"Error checking if {timeframe} calculation needed: {e}")
            return True  # Assume calculation needed on error
    


# Global instance
postgres_indicator_service = PostgresIndicatorService()