"""
Dynamic Indicator Checker Service
Checks if dynamic indicators are actually calculated and stored in the database
"""

import logging
from typing import List, Set, Dict, Any
from services.ultra_fast_database_service import ultra_fast_db as high_speed_db
from services.dynamic_indicator_manager import dynamic_indicator_manager

logger = logging.getLogger(__name__)

class DynamicIndicatorChecker:
    """Service to check and ensure dynamic indicators are calculated before queries"""
    
    async def check_and_calculate_indicators(self, required_fields: Set[str]) -> Dict[str, Any]:
        """
        Check if required indicators exist in database and calculate if missing
        
        Args:
            required_fields: Set of field names required by the query
            
        Returns:
            Dict with status and list of calculated indicators
        """
        try:
            logger.info(f"Checking indicators: {required_fields}")
            
            # Filter out basic fields that don't need calculation
            basic_fields = {'open', 'high', 'low', 'close', 'volume', 'symbol', 'timestamp', 'datetime'}
            indicator_fields = required_fields - basic_fields
            
            if not indicator_fields:
                return {"status": "success", "message": "No indicators to check", "calculated": []}
            
            calculated_indicators = []
            
            # Check each indicator field
            for field in indicator_fields:
                # Skip timeframe-prefixed basic fields
                if any(field.endswith(f"_{bf}") for bf in ['open', 'high', 'low', 'close', 'volume']):
                    continue
                
                # Check if this is a dynamic indicator (contains parameter info)
                if self._is_dynamic_indicator(field):
                    # Check if it exists in database
                    exists = await self._check_indicator_in_database(field)
                    
                    if not exists:
                        logger.info(f"Dynamic indicator {field} not found in database, calculating...")
                        
                        # Parse indicator parameters from field name
                        indicator_config = self._parse_indicator_field(field)
                        
                        if indicator_config:
                            # Use dynamic indicator manager for all indicators
                            success = await dynamic_indicator_manager.add_custom_indicator(
                                name=indicator_config['name'],
                                params=indicator_config['params'],
                                timeframe=indicator_config.get('timeframe', 'daily')
                            )
                            
                            if success:
                                calculated_indicators.append(field)
                                logger.info(f"Successfully calculated {field}")
                            else:
                                logger.error(f"Failed to calculate {field}")
                    else:
                        logger.info(f"Indicator {field} already exists in database")
            
            return {
                "status": "success",
                "message": f"Checked {len(indicator_fields)} indicators",
                "calculated": calculated_indicators,
                "total_checked": len(indicator_fields)
            }
            
        except Exception as e:
            logger.error(f"Error checking indicators: {e}")
            return {
                "status": "error",
                "message": str(e),
                "calculated": []
            }
    
    def _is_dynamic_indicator(self, field: str) -> bool:
        """Check if a field is a dynamic indicator"""
        # Dynamic indicators typically have parameter info in the name
        indicators = ['supertrend', 'rsi', 'sma', 'ema', 'macd', 'bollinger']
        return any(ind in field.lower() for ind in indicators)
    
    async def _check_indicator_in_database(self, field: str) -> bool:
        """Check if an indicator exists in the database JSONB column"""
        try:
            if not high_speed_db.pool:
                await high_speed_db.initialize()
            
            async with high_speed_db.pool.acquire() as conn:
                # Check if any row has this indicator in JSONB
                count = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM daily_candles 
                    WHERE indicators ? $1
                    LIMIT 1
                """, field)
                
                return count > 0
                
        except Exception as e:
            logger.error(f"Error checking indicator in database: {e}")
            return False
    
    def _parse_indicator_field(self, field: str) -> Dict[str, Any]:
        """Parse indicator field name to extract parameters"""
        try:
            field_lower = field.lower()
            
            # Parse SuperTrend indicators
            if 'supertrend' in field_lower:
                # Examples: supertrend indicators with various parameters
                # Remove timeframe prefixes and direction suffix
                parts = field_lower.replace('daily_', '').replace('weekly_', '').replace('monthly_', '')
                parts = parts.replace('supertrend_', '').replace('_direction', '')
                
                # Split by underscore to get period and multiplier
                param_parts = parts.split('_')
                if len(param_parts) >= 2:
                    period = int(param_parts[0])
                    
                    # Handle decimal multiplier formatting (e.g., "2dot5" -> 2.5, "3" -> 3.0)
                    multiplier_str = param_parts[1]
                    if 'dot' in multiplier_str:
                        multiplier = float(multiplier_str.replace('dot', '.'))
                    else:
                        multiplier = float(multiplier_str)
                    
                    # Determine timeframe
                    timeframe = 'daily'
                    if 'weekly' in field_lower:
                        timeframe = 'weekly'
                    elif 'monthly' in field_lower:
                        timeframe = 'monthly'
                    
                    return {
                        "name": "SuperTrend",
                        "params": {"period": period, "multiplier": multiplier},
                        "timeframe": timeframe
                    }
            
            # Parse RSI indicators
            elif 'rsi' in field_lower:
                # Example: rsi indicators with various periods
                parts = field_lower.replace('daily_', '').replace('weekly_', '').replace('monthly_', '')
                parts = parts.replace('rsi_', '')
                
                if parts.isdigit():
                    period = int(parts)
                    
                    timeframe = 'daily'
                    if 'weekly' in field_lower:
                        timeframe = 'weekly'
                    elif 'monthly' in field_lower:
                        timeframe = 'monthly'
                    
                    return {
                        "name": "RSI",
                        "params": {"period": period},
                        "timeframe": timeframe
                    }
            
            # Parse SMA indicators
            elif 'sma' in field_lower:
                # Example: sma indicators with various periods
                parts = field_lower.replace('daily_', '').replace('weekly_', '').replace('monthly_', '')
                parts = parts.replace('sma_', '')
                
                if parts.isdigit():
                    period = int(parts)
                    
                    timeframe = 'daily'
                    if 'weekly' in field_lower:
                        timeframe = 'weekly'
                    elif 'monthly' in field_lower:
                        timeframe = 'monthly'
                    
                    return {
                        "name": "SMA",
                        "params": {"period": period},
                        "timeframe": timeframe
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing indicator field {field}: {e}")
            return None

# Global instance
dynamic_indicator_checker = DynamicIndicatorChecker()