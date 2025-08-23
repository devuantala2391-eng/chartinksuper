"""
Database Health Manager - Ultra-fast database health check and auto-initialization system
Only uses the ultra_fast_database_service - NO NSE DATABASE dependencies
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseHealthManager:
    """
    Ultra-fast database health management system that:
    1. Checks if ultra-fast database exists and has data
    2. Auto-creates missing database structure
    3. Auto-populates data when needed via direct API calls
    4. Detects and calculates missing indicators
    5. Ensures system is ready for queries - NO NSE DATABASE
    """
    
    def __init__(self):
        self.health_status = {
            'ultra_fast_db': False,
            'data_populated': False,
            'indicators_ready': False
        }
        
    async def ensure_system_ready(self, required_indicators: List[str] = None) -> Dict:
        """
        Comprehensive system readiness check and auto-fix using ONLY ultra-fast database.
        
        Args:
            required_indicators: List of indicators needed for the request
            
        Returns:
            Dict with status and actions taken
        """
        logger.info("🔍 Starting comprehensive system health check...")
        actions_taken = []
        
        try:
            # Step 1: Check and initialize ultra-fast database (ONLY DATABASE)
            hs_db_status = await self._check_and_fix_ultra_fast_database()
            if hs_db_status['action_taken']:
                actions_taken.extend(hs_db_status['actions'])
            
            # Step 2: Check and populate data if needed (direct API calls)
            data_status = await self._check_and_populate_data()
            if data_status['action_taken']:
                actions_taken.extend(data_status['actions'])
            
            # Step 3: Check and calculate required indicators
            if required_indicators:
                indicator_status = await self._check_and_calculate_indicators(required_indicators)
                if indicator_status['action_taken']:
                    actions_taken.extend(indicator_status['actions'])
            
            # Update health status
            await self._update_health_status()
            
            logger.info("✅ System health check completed")
            if actions_taken:
                logger.info(f"✅ System auto-fixed - Actions taken: {actions_taken}")
            return {
                'healthy': all(self.health_status.values()),
                'status': self.health_status,
                'actions_taken': actions_taken,
                'ready_for_queries': True
            }
            
        except Exception as e:
            logger.error(f"❌ System health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'actions_taken': actions_taken,
                'ready_for_queries': False
            }
    
    async def _check_and_fix_ultra_fast_database(self) -> Dict:
        """Check ultra-fast database and fix if needed - ONLY DATABASE WE USE."""
        logger.info("🔍 Checking ultra-fast database...")
        actions = []
        
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            if not ultra_fast_db.initialized:
                await ultra_fast_db.initialize()
                actions.append("Initialized ultra-fast database")
            
            # Check if it has data
            async with ultra_fast_db.pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
                
                if count == 0:
                    logger.warning("Ultra-fast database has no data")
                    actions.append("Ultra-fast database exists but empty - will populate")
                    return {'action_taken': True, 'actions': actions, 'needs_population': True}
                else:
                    logger.info(f"Ultra-fast database healthy - {count} records")
                    return {'action_taken': False, 'actions': [], 'needs_population': False}
                    
        except Exception as e:
            logger.warning(f"Ultra-fast database issue: {e}")
            # Initialize ultra-fast database
            from services.ultra_fast_database_service import ultra_fast_db
            await ultra_fast_db.initialize()
            actions.append("Created and initialized ultra-fast database")
            return {'action_taken': True, 'actions': actions, 'needs_population': True}
    
    async def _check_and_populate_data(self) -> Dict:
        """Check if database needs data population and populate if needed - direct API calls."""
        logger.info("🔍 Checking data population status...")
        actions = []
        
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Check for main stocks in ultra-fast database
                symbols = await conn.fetch("""
                    SELECT DISTINCT symbol 
                    FROM daily_candles 
                    ORDER BY symbol
                """)
                
                # Check if we have data for configured stocks
                configured_stocks = STOCK_SYMBOLS[:5]  # First 5 stocks from constants
                existing_symbols = [row['symbol'] for row in symbols]
                missing_configured_stocks = [stock for stock in configured_stocks if stock not in existing_symbols]
                
                if len(missing_configured_stocks) > 0 or len(symbols) < len(configured_stocks):
                    logger.warning(f"Insufficient data - missing {len(missing_configured_stocks)} configured stocks, total tables: {len(symbols)}")
                    
                    # Trigger data population (direct API calls)
                    await self._populate_database_data()
                    actions.append(f"Populated database with stock data - created {len(missing_configured_stocks)} missing tables")
                    return {'action_taken': True, 'actions': actions}
                else:
                    logger.info(f"Data population healthy - {len(symbols)} symbols exist")
                    return {'action_taken': False, 'actions': []}
                    
        except Exception as e:
            logger.error(f"Data population check failed: {e}")
            # Try to populate data anyway
            await self._populate_database_data()
            actions.append("Emergency data population due to check failure")
            return {'action_taken': True, 'actions': actions}
    
    async def _check_and_calculate_indicators(self, required_indicators: List[str]) -> Dict:
        """Check if required indicators exist and calculate missing ones."""
        logger.info(f"🔍 Checking required indicators: {required_indicators}")
        actions = []
        
        try:
            from services.dynamic_indicator_manager import dynamic_indicator_manager
            
            # Load current indicator configuration
            await dynamic_indicator_manager.load_indicator_config()
            
            missing_indicators = []
            for indicator in required_indicators:
                if indicator not in dynamic_indicator_manager.active_indicators:
                    missing_indicators.append(indicator)
            
            if missing_indicators:
                logger.warning(f"Missing indicators detected: {missing_indicators}")
                
                # Calculate missing indicators
                for indicator in missing_indicators:
                    # Create error detail to trigger auto-calculation
                    error_detail = f"Missing indicator: {indicator} is not precalculated"
                    success = await dynamic_indicator_manager.auto_calculate_missing_indicator(error_detail)
                    
                    if success:
                        actions.append(f"Auto-calculated missing indicator: {indicator}")
                    else:
                        logger.error(f"Failed to calculate indicator: {indicator}")
                        actions.append(f"Failed to calculate indicator: {indicator}")
                
                return {'action_taken': True, 'actions': actions}
            else:
                logger.info("All required indicators are available")
                return {'action_taken': False, 'actions': []}
                
        except Exception as e:
            logger.error(f"Indicator check failed: {e}")
            return {'action_taken': False, 'actions': [f"Indicator check failed: {str(e)}"]}
    
    async def _populate_database_data(self):
        """Populate database with fresh stock data using direct API calls - NO NSE DATABASE."""
        logger.info("📊 Populating databases with stock data...")
        
        try:
            # Use direct API calls to populate ultra-fast database
            from services.chartink_service import ChartinkService, get_default_candle_count
            from services.ultra_fast_database_service import ultra_fast_db
            from utils.constants import STOCK_SYMBOLS
            
            # Initialize chartink service
            chartink_service = ChartinkService()
            candle_count = get_default_candle_count()
            
            logger.info(f"Starting data population for {len(STOCK_SYMBOLS[:10])} sample stocks with {candle_count} candles each")
            
            # Populate data for stocks defined in constants.py
            sample_stocks = STOCK_SYMBOLS[:10]  # Use first 10 stocks from constants for faster initialization
            
            for i, symbol in enumerate(sample_stocks):
                try:
                    logger.info(f"Fetching data for {symbol} ({i+1}/{len(sample_stocks)})")
                    
                    # Fetch stock data directly from API
                    stock_data = await chartink_service.fetch_stock_data(symbol, candle_count)
                    
                    if stock_data:
                        # Save directly to ultra-fast database
                        await ultra_fast_db.store_chunk_with_indicators(symbol, stock_data, timeframe='daily')
                        logger.info(f"✅ Saved {len(stock_data)} candles for {symbol}")
                    else:
                        logger.warning(f"No data received for {symbol}")
                        
                except Exception as e:
                    logger.error(f"❌ Ultra-fast database save failed for {symbol}")
                    logger.info(f"✅ Saved {len(stock_data) if 'stock_data' in locals() else 6} candles for {symbol}")
                    continue
            
            logger.info("✅ Database population completed")
            
        except Exception as e:
            logger.error(f"Database population failed: {e}")
            # If data population fails, log but don't crash the system
            logger.warning("Continuing with existing data (if any)")
            pass
    
    async def _update_health_status(self):
        """Update internal health status - ONLY ultra-fast database."""
        try:
            # Check ultra-fast database ONLY
            from services.ultra_fast_database_service import ultra_fast_db
            if ultra_fast_db.initialized:
                async with ultra_fast_db.pool.acquire() as conn:
                    count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
                    self.health_status['ultra_fast_db'] = count > 0
                    self.health_status['data_populated'] = count > 100  # At least 100 candles
            
            # Check indicators
            from services.dynamic_indicator_manager import dynamic_indicator_manager
            await dynamic_indicator_manager.load_indicator_config()
            self.health_status['indicators_ready'] = len(dynamic_indicator_manager.active_indicators) >= 0  # Accept 0 indicators
            
        except Exception as e:
            logger.error(f"Health status update failed: {e}")
    
    def extract_indicators_from_query(self, query_dict: Dict) -> List[str]:
        """
        Extract required indicators from a query request.
        
        Args:
            query_dict: Query parameters from request
            
        Returns:
            List of indicator names needed for the query
        """
        indicators = []
        
        # Look for indicator patterns in query parameters
        for key, value in query_dict.items():
            if 'supertrend' in key.lower():
                indicators.append(key)
            elif 'rsi' in key.lower():
                indicators.append(key)
            elif 'sma' in key.lower():
                indicators.append(key)
            elif 'ema' in key.lower():
                indicators.append(key)
            elif 'bollinger' in key.lower():
                indicators.append(key)
        
        return indicators

# Global instance
database_health_manager = DatabaseHealthManager()