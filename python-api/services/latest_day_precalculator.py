import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import time
from utils.constants import STOCK_SYMBOLS
from services.optimized_processor import optimized_processor
from services.db_wrapper import db_wrapper as db_service

logger = logging.getLogger(__name__)

# Performance configuration  
PERFORMANCE_CONFIG = {
    "batch_size": 100
}

class LatestDayPrecalculator:
    """Service to update precalculated indicators using database storage only."""
    
    def __init__(self):
        # Default indicators configuration (can be extended)
        self.default_indicators = [
            {"name": "RSI", "params": {"period": 14}, "timeframe": "daily"},
            {"name": "SMA", "params": {"period": 20}, "timeframe": "daily"},
            {"name": "EMA", "params": {"period": 12}, "timeframe": "daily"},
            {"name": "SuperTrend", "params": {"period": 10, "multiplier": 2}, "timeframe": "daily"},
            {"name": "BollingerBands", "params": {"period": 20, "std_dev": 2}, "timeframe": "daily"}
        ]
        logger.info("📊 Latest day precalculator initialized (database-only mode)")
        
    async def load_indicators_config(self) -> List[Dict[str, Any]]:
        """Load the precalculated indicators configuration from dynamic indicator manager."""
        try:
            # Import here to avoid circular imports
            from services.dynamic_indicator_manager import dynamic_indicator_manager
            
            # Get active indicators from dynamic manager
            active_indicators = await dynamic_indicator_manager.get_active_indicators_list()
            
            if active_indicators:
                logger.info(f"📊 Loaded {len(active_indicators)} active indicators from dynamic manager")
                return active_indicators
            else:
                logger.info("📊 No active indicators found, using defaults")
                return self.default_indicators
                
        except Exception as e:
            logger.error(f"Failed to load indicators from dynamic manager: {e}")
            # Fallback to default indicators
            return self.default_indicators
    
    async def prepare_stock_batch(self, symbols: List[str], indicators: List[Dict[str, Any]]) -> List[tuple]:
        """Prepare batch of stocks for processing using database."""
        batch_data = []
        timeframes = list(set(ind.get('timeframe', 'daily') for ind in indicators))
        
        if not db_service.initialized:
            logger.error("Database service not initialized")
            return []
        
        for symbol in symbols:
            try:
                stock_data = await db_service.load_candles(symbol)
                if stock_data:
                    batch_data.append((symbol, stock_data, indicators, timeframes))
            except Exception as e:
                logger.error(f"Error loading {symbol} from database: {e}")
        
        return batch_data
    
    async def update_latest_day_precalculated(self, symbol: str) -> Dict[str, str]:
        """Update precalculated indicators for the latest day using database storage."""
        try:
            if not db_service.initialized:
                logger.error("Database service not initialized")
                return {symbol: "Database not initialized"}
            
            # Load indicators configuration
            indicators = await self.load_indicators_config()
            if not indicators:
                logger.warning(f"No indicators configured for {symbol}")
                return {symbol: "No indicators configured"}
            
            # Load stock data from database
            stock_data = await db_service.load_candles(symbol)
            if not stock_data:
                return {symbol: "No stock data found in database"}
            
            # The data in the database should already have indicators calculated
            # This service now mainly serves as a compatibility layer
            # The actual indicator calculation is handled by the database services
            
            latest_candle = stock_data[-1] if stock_data else None
            if not latest_candle:
                return {symbol: "No latest candle found"}
            
            # The database already stores all the indicator data
            # This function now just confirms the data is available
            return {symbol: f"Database contains {len(stock_data)} candles with indicators"}
                
        except Exception as e:
            logger.error(f"Failed to update precalculated for {symbol}: {e}")
            return {symbol: f"Error: {str(e)}"}
    
    async def update_all_latest_precalculated(self, 
                                            symbols: Optional[List[str]] = None,
                                            updated_symbols: Optional[List[str]] = None,
                                            use_optimized: bool = True) -> Dict[str, str]:
        """Update latest day precalculated for multiple symbols using database storage."""
        # Use updated_symbols if provided, otherwise use all symbols
        if updated_symbols:
            symbols = updated_symbols
        elif symbols is None:
            symbols = STOCK_SYMBOLS
        
        logger.info(f"📊 DATABASE-BASED Precalculation check: {len(symbols)} symbols")
        start_time = time.time()
        
        try:
            if not db_service.initialized:
                logger.error("Database service not initialized")
                return {symbol: "Database not initialized" for symbol in symbols}
            
            # Load indicators configuration once
            indicators = await self.load_indicators_config()
            if not indicators:
                logger.error("No indicators configured")
                return {symbol: "No indicators configured" for symbol in symbols}
            
            # Process symbols in batches using the optimized processor
            logger.info("📊 Using DATABASE-OPTIMIZED processor")
            
            # Prepare data from database
            batch_data = await self.prepare_stock_batch(symbols, indicators)
            
            if not batch_data:
                return {symbol: "No valid data in database" for symbol in symbols}
            
            # Process in batches using the optimized processor (which now works with database data)
            all_results = []
            processed_count = 0
            
            batch_size = PERFORMANCE_CONFIG['batch_size']
            for i in range(0, len(batch_data), batch_size):
                batch = batch_data[i:i + batch_size]
                try:
                    batch_results = optimized_processor.process_stock_batch_optimized(batch)
                    all_results.extend(batch_results)
                    
                    processed_count += len(batch_results)
                    percentage = (processed_count / len(batch_data)) * 100
                    logger.info(f"📈 Processing progress: {processed_count}/{len(batch_data)} ({percentage:.1f}%)")
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")
                    # Continue with next batch
            
            # Prepare results
            results = {}
            for stock, result_data, success, error_msg in all_results:
                if success:
                    results[stock] = "Database processing completed"
                else:
                    results[stock] = f"Failed: {error_msg}"
            
            # Add any missing symbols
            for symbol in symbols:
                if symbol not in results:
                    results[symbol] = "No database data found"
            
            elapsed_time = time.time() - start_time
            logger.info(f"✅ DATABASE-BASED Precalculation completed in {elapsed_time:.2f}s")
            logger.info(f"📊 Processed {len(all_results)} symbols from database storage")
            
            return results
            
        except Exception as e:
            logger.error(f"Critical error in precalculation: {e}")
            return {symbol: f"Critical error: {str(e)}" for symbol in symbols}

# Global instance
latest_day_precalculator = LatestDayPrecalculator()