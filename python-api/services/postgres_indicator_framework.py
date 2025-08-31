"""
PostgreSQL Indicator Framework
Extensible framework for managing all indicator calculations via PostgreSQL stored procedures
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
from enum import Enum
from services.postgres_indicator_service import postgres_indicator_service

logger = logging.getLogger(__name__)

class IndicatorType(Enum):
    """Types of indicators supported by the framework"""
    PERCENTAGE_CHANGE = "PercentageChange"
    MOVING_AVERAGE = "MovingAverage"
    RSI = "RSI"
    SUPERTREND = "SuperTrend"
    BOLLINGER_BANDS = "BollingerBands"
    MACD = "MACD"
    STOCHASTIC = "Stochastic"
    VOLUME = "Volume"

class PostgresIndicatorFramework:
    """
    Framework for managing indicator calculations via PostgreSQL stored procedures
    
    This framework provides:
    1. Registry of available indicators and their PostgreSQL implementations
    2. Automatic routing to PostgreSQL vs Python based on availability
    3. Easy extension for future indicator migrations
    4. Performance monitoring and logging
    5. Fallback mechanisms
    """
    
    def __init__(self):
        self.postgres_indicators = {}
        self.fallback_handlers = {}
        self._initialize_indicator_registry()
    
    def _initialize_indicator_registry(self):
        """Initialize the registry of PostgreSQL-supported indicators"""
        
        # Register percentage change indicators (already migrated)
        self.postgres_indicators[IndicatorType.PERCENTAGE_CHANGE] = {
            "handler": self._handle_percentage_change,
            "supported_timeframes": ["daily", "weekly", "monthly"],
            "description": "High-performance percentage change calculation via PostgreSQL",
            "migration_date": "2025-08-24",
            "performance_gain": "90%+ faster than Python"
        }
        
        # Register volume indicators (using dynamic sliding window approach)
        self.postgres_indicators[IndicatorType.VOLUME] = {
            "handler": self._handle_volume,
            "supported_timeframes": ["weekly", "monthly"],
            "description": "Dynamic sliding window volume calculation via PostgreSQL",
            "migration_date": "2025-08-29",
            "performance_gain": "95%+ faster than Python, stores cumulative sliding window values"
        }
        
        # Register SuperTrend indicator (with direction)
        self.postgres_indicators[IndicatorType.SUPERTREND] = {
            "handler": self._handle_supertrend,
            "supported_timeframes": ["daily"],
            "description": "PostgreSQL-based SuperTrend calculation with 2-decimal precision and direction",
            "migration_date": "2025-08-30",
            "performance_gain": "90%+ faster than Python, calculates both value and direction"
        }
        
        # Future indicators can be added here as they are migrated
        # Example for future migrations:
        
        # self.postgres_indicators[IndicatorType.MOVING_AVERAGE] = {
        #     "handler": self._handle_moving_average,
        #     "supported_timeframes": ["daily", "weekly", "monthly"],
        #     "description": "PostgreSQL-based SMA/EMA calculation",
        #     "migration_date": "TBD",
        #     "performance_gain": "Estimated 80%+ faster"
        # }
        
        # self.postgres_indicators[IndicatorType.RSI] = {
        #     "handler": self._handle_rsi,
        #     "supported_timeframes": ["daily", "weekly"],
        #     "description": "PostgreSQL-based RSI calculation with window functions",
        #     "migration_date": "TBD", 
        #     "performance_gain": "Estimated 85%+ faster"
        # }
    
    async def calculate_indicator(
        self, 
        indicator_def: Dict[str, Any],
        fallback_handler: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for indicator calculation
        
        Args:
            indicator_def: Indicator definition with name, timeframe, params
            fallback_handler: Python fallback function if PostgreSQL not available
            
        Returns:
            Dict with calculation results and performance metrics
        """
        indicator_name = indicator_def.get("name")
        timeframe = indicator_def.get("timeframe", "daily")
        
        # Try to map indicator name to enum
        indicator_type = self._get_indicator_type(indicator_name)
        
        if not indicator_type:
            logger.warning(f"Unknown indicator type: {indicator_name}")
            return await self._use_fallback(indicator_def, fallback_handler)
        
        # Check if PostgreSQL implementation is available
        if indicator_type in self.postgres_indicators:
            postgres_info = self.postgres_indicators[indicator_type]
            
            # Check if timeframe is supported
            if timeframe not in postgres_info["supported_timeframes"]:
                logger.warning(f"{indicator_name} PostgreSQL implementation doesn't support {timeframe} timeframe")
                return await self._use_fallback(indicator_def, fallback_handler)
            
            # Use PostgreSQL implementation
            logger.info(f"🚀 Using PostgreSQL implementation for {indicator_name} ({timeframe})")
            logger.info(f"📊 Expected performance gain: {postgres_info['performance_gain']}")
            
            try:
                handler = postgres_info["handler"]
                result = await handler(indicator_def)
                
                result["calculation_method"] = "PostgreSQL"
                result["framework_version"] = "1.0"
                return result
                
            except Exception as e:
                logger.error(f"PostgreSQL calculation failed for {indicator_name}: {e}")
                logger.info(f"🔄 Falling back to Python implementation")
                return await self._use_fallback(indicator_def, fallback_handler)
        
        else:
            # No PostgreSQL implementation available, use fallback
            logger.info(f"📝 No PostgreSQL implementation available for {indicator_name}, using Python fallback")
            return await self._use_fallback(indicator_def, fallback_handler)
    
    def _get_indicator_type(self, indicator_name: str) -> Optional[IndicatorType]:
        """Map indicator name to IndicatorType enum"""
        name_mapping = {
            "PercentageChange": IndicatorType.PERCENTAGE_CHANGE,
            "SMA": IndicatorType.MOVING_AVERAGE,
            "EMA": IndicatorType.MOVING_AVERAGE,
            "RSI": IndicatorType.RSI,
            "SuperTrend": IndicatorType.SUPERTREND,
            "BollingerBands": IndicatorType.BOLLINGER_BANDS,
            "MACD": IndicatorType.MACD,
            "Stochastic": IndicatorType.STOCHASTIC,
            "Volume": IndicatorType.VOLUME
        }
        
        return name_mapping.get(indicator_name)
    
    async def _use_fallback(
        self, 
        indicator_def: Dict[str, Any],
        fallback_handler: Optional[Callable]
    ) -> Dict[str, Any]:
        """Use Python fallback implementation"""
        
        if fallback_handler:
            try:
                result = await fallback_handler(indicator_def)
                if isinstance(result, bool):
                    # Convert boolean to standard format
                    result = {
                        "success": result,
                        "calculation_method": "Python_Fallback",
                        "indicator_name": indicator_def.get("name"),
                        "timeframe": indicator_def.get("timeframe", "daily")
                    }
                elif isinstance(result, dict):
                    result["calculation_method"] = "Python_Fallback"
                
                return result
                
            except Exception as e:
                logger.error(f"Fallback handler failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "calculation_method": "Failed_Fallback"
                }
        else:
            logger.error("No fallback handler provided and no PostgreSQL implementation available")
            return {
                "success": False,
                "error": "No implementation available",
                "calculation_method": "None"
            }
    
    # PostgreSQL Handler Methods
    
    async def _handle_percentage_change(self, indicator_def: Dict[str, Any]) -> Dict[str, Any]:
        """Handle percentage change calculation via PostgreSQL"""
        timeframe = indicator_def.get('timeframe', 'daily')
        
        # Initialize PostgreSQL service
        await postgres_indicator_service.initialize()
        
        # Check if calculation is needed
        if not await postgres_indicator_service.is_calculation_needed(timeframe, threshold_percentage=95.0):
            logger.info(f"✅ {timeframe.title()} percentage change already has sufficient coverage")
            return {
                "success": True,
                "skipped": True,
                "reason": "Sufficient coverage exists",
                "timeframe": timeframe
            }
        
        # Execute calculation
        result = await postgres_indicator_service.calculate_percentage_change(timeframe)
        return result
    
    async def _handle_volume(self, indicator_def: Dict[str, Any]) -> Dict[str, Any]:
        """Handle volume calculation via PostgreSQL with dynamic sliding window"""
        timeframe = indicator_def.get('timeframe', 'weekly')
        
        # Validate timeframe for volume indicators
        if timeframe not in ['weekly', 'monthly']:
            return {
                "success": False,
                "error": f"Volume indicators only support weekly and monthly timeframes, got: {timeframe}",
                "calculation_method": "PostgreSQL"
            }
        
        # Initialize PostgreSQL service
        await postgres_indicator_service.initialize()
        
        # Execute volume calculation using dynamic sliding window
        result = await postgres_indicator_service.calculate_volume(timeframe=timeframe)
        return result
    
    # Placeholder methods for future indicator implementations
    
    async def _handle_moving_average(self, indicator_def: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder for PostgreSQL moving average implementation"""
        raise NotImplementedError("Moving average PostgreSQL implementation not yet available")
    
    async def _handle_rsi(self, indicator_def: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder for PostgreSQL RSI implementation"""
        raise NotImplementedError("RSI PostgreSQL implementation not yet available")
    
    async def _handle_supertrend(self, indicator_def: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle SuperTrend calculation via PostgreSQL stored procedure
        
        Calculates both SuperTrend value (2 decimal precision) and direction (1=up, 0=down)
        """
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            if not ultra_fast_db.initialized:
                await ultra_fast_db.initialize()
            
            # Generate indicator key from definition
            params = indicator_def.get('params', {})
            period = params.get('period', 10)
            multiplier = params.get('multiplier', 3.0)
            
            # Format multiplier for key generation
            if multiplier == int(multiplier):
                multiplier_str = str(int(multiplier))
            else:
                multiplier_str = str(multiplier).replace('.', 'dot')
            
            indicator_key = f"supertrend_{period}_{multiplier_str}"
            
            logger.info(f"Calculating SuperTrend via PostgreSQL: {indicator_key}")
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Call the dynamic SuperTrend handler
                result = await conn.fetchrow(
                    "SELECT * FROM calculate_dynamic_supertrend($1)",
                    indicator_key
                )
                
                if result and result['success']:
                    logger.info(f"✅ SuperTrend calculation successful: {result['message']}")
                    logger.info(f"   Generated indicators: {result['indicator_key']} and {result['direction_key']}")
                    logger.info(f"   Symbols processed: {result['symbols_processed']}, Updated: {result['symbols_updated']}")
                    
                    return {
                        "success": True,
                        "calculation_method": "PostgreSQL",
                        "indicator_key": result['indicator_key'],
                        "direction_key": result['direction_key'],
                        "symbols_processed": result['symbols_processed'],
                        "symbols_updated": result['symbols_updated'],
                        "message": result['message']
                    }
                else:
                    error_msg = result['message'] if result else "Unknown error"
                    logger.error(f"❌ SuperTrend calculation failed: {error_msg}")
                    return {
                        "success": False,
                        "calculation_method": "PostgreSQL",
                        "error": error_msg
                    }
                    
        except Exception as e:
            logger.error(f"Error in SuperTrend PostgreSQL handler: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "calculation_method": "PostgreSQL",
                "error": str(e)
            }
    
    # Utility Methods
    
    def get_postgres_indicators_info(self) -> Dict[str, Dict]:
        """Get information about all PostgreSQL-supported indicators"""
        info = {}
        for indicator_type, details in self.postgres_indicators.items():
            info[indicator_type.value] = {
                "supported_timeframes": details["supported_timeframes"],
                "description": details["description"],
                "migration_date": details["migration_date"],
                "performance_gain": details["performance_gain"]
            }
        return info
    
    def is_postgres_supported(self, indicator_name: str, timeframe: str = "daily") -> bool:
        """Check if an indicator has PostgreSQL support for the given timeframe"""
        indicator_type = self._get_indicator_type(indicator_name)
        
        if not indicator_type or indicator_type not in self.postgres_indicators:
            return False
        
        supported_timeframes = self.postgres_indicators[indicator_type]["supported_timeframes"]
        return timeframe in supported_timeframes
    
    async def get_framework_status(self) -> Dict[str, Any]:
        """Get comprehensive framework status"""
        postgres_count = len(self.postgres_indicators)
        total_indicators = len(IndicatorType)
        migration_percentage = (postgres_count / total_indicators) * 100
        
        return {
            "total_indicator_types": total_indicators,
            "postgres_migrated": postgres_count,
            "migration_percentage": round(migration_percentage, 1),
            "supported_indicators": self.get_postgres_indicators_info(),
            "framework_initialized": True
        }

# Global instance
postgres_indicator_framework = PostgresIndicatorFramework()