"""
High-Speed Query Validator with Dynamic Indicator Support
Validates queries against high-speed database and triggers dynamic calculation when needed
"""

import asyncio
import asyncpg
import logging
from typing import Dict, List, Set, Any, Optional
from services.dynamic_indicator_manager import dynamic_indicator_manager
from services.ultra_fast_database_service import ultra_fast_db as high_speed_db
from services.utils import format_multiplier_for_key, format_period_for_key
import re

logger = logging.getLogger(__name__)

class HighSpeedQueryValidator:
    """Validates queries and ensures indicators exist in high-speed database"""
    
    def __init__(self):
        self.static_fields = {
            'open', 'high', 'low', 'close', 'volume', 
            'timestamp', 'datetime', 'symbol'
            # Physical indicator columns removed - all indicators now in JSONB
        }
    
    async def validate_and_prepare_indicators(self, parsed_query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate query fields and prepare missing indicators dynamically.
        
        Returns:
            Dict with validation status and any calculated indicators
        """
        try:
            # Extract required fields from query
            required_fields = self._extract_required_fields(parsed_query)
            logger.info(f"Query requires fields: {required_fields}")
            
            # Check which fields exist in database
            existing_fields = await self._check_existing_fields()
            missing_fields = required_fields - existing_fields
            
            if not missing_fields:
                logger.info("All required fields exist")
                return {
                    "valid": True,
                    "required_fields": list(required_fields),
                    "message": "All fields available"
                }
            
            logger.info(f"Missing fields: {missing_fields}")
            
            # Try to calculate missing indicators automatically
            logger.info(f"Attempting to auto-calculate missing indicators: {missing_fields}")
            calculated = await self._calculate_missing_indicators(missing_fields)
            
            if calculated and len(calculated) > 0:
                logger.info(f"Successfully auto-calculated {len(calculated)} indicators: {[c.get('name', 'Unknown') for c in calculated]}")
                return {
                    "valid": True,
                    "required_fields": list(required_fields),
                    "message": f"Auto-calculated {len(calculated)} missing indicators",
                    "calculated_indicators": calculated
                }
            
            # If auto-calculation failed, provide clear error message
            # Format field names for display (replace underscores with spaces)
            indicator_names = [f.replace('_', ' ') for f in missing_fields]
            return {
                "valid": False,
                "error": f"Required indicators not found: {', '.join(indicator_names)}",
                "details": "Could not auto-calculate missing indicators. Please check the indicator definitions.",
                "missing_fields": list(missing_fields),
                "available_fields": list(existing_fields),
                "suggestion": "Verify indicator names and try again",
                "calculated_attempt": len(calculated) if calculated else 0
            }
                
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    def _extract_required_fields(self, parsed_query: Dict[str, Any]) -> Set[str]:
        """Extract all field names required by the query"""
        required_fields = set()
        conditions = parsed_query.get("conditions", [])
        
        for condition in conditions:
            # Extract from left side
            left = condition.get("left", {})
            if left.get("field"):
                field = self._normalize_field_name(left["field"])
                required_fields.add(field)
            
            # Extract from right side if it's a field
            right = condition.get("right", {})
            if right.get("type") == "field" and right.get("field"):
                field = self._normalize_field_name(right["field"])
                required_fields.add(field)
        
        return required_fields
    
    def _normalize_field_name(self, field_name: str) -> str:
        """Normalize field name to match database storage format"""
        # Handle SuperTrend with decimal parameters
        # Keep ALL timeframe prefixes: daily_, weekly_, monthly_
        
        # Handle SMA function notation: sma(20) -> sma_20
        if field_name.startswith('sma(') and field_name.endswith(')'):
            period = field_name[4:-1]  # Extract period between sma( and )
            return f"sma_{period}"
        
        # Handle EMA function notation: ema(10) -> ema_10
        if field_name.startswith('ema(') and field_name.endswith(')'):
            period = field_name[4:-1]  # Extract period between ema( and )
            return f"ema_{period}"
        
        # Handle timeframed SMA: weekly_sma(20) -> weekly_sma_20
        for timeframe in ['daily_', 'weekly_', 'monthly_']:
            if field_name.startswith(f'{timeframe}sma(') and field_name.endswith(')'):
                period = field_name[len(f'{timeframe}sma('):-1]
                return f"{timeframe}sma_{period}"
            if field_name.startswith(f'{timeframe}ema(') and field_name.endswith(')'):
                period = field_name[len(f'{timeframe}ema('):-1]
                return f"{timeframe}ema_{period}"
        
        # Handle percentage change indicators - NEW FORMAT: daily_pctchg, weekly_pctchg, monthly_pctchg
        # Convert legacy format daily_pctchg_1 -> daily_pctchg (remove the _1 parameter)
        if 'pctchg' in field_name:
            # Remove legacy _1 parameter suffix if present
            if field_name.endswith('_1'):
                field_name = field_name[:-2]  # Remove the '_1' suffix
            return field_name
        
        # Handle ALL timeframed SuperTrend - keep timeframe prefix
        if field_name.startswith(('daily_', 'weekly_', 'monthly_')):
            if 'supertrend_' in field_name:
                parts = field_name.split('_')
                if len(parts) >= 4:  # timeframed supertrend with period and multiplier
                    # Use utility function to format multiplier properly
                    timeframe = parts[0]
                    period = parts[2]
                    multiplier = parts[3].replace('dot', '.')
                    period_str = format_period_for_key(float(period))
                    multiplier_str = format_multiplier_for_key(float(multiplier))
                    return f"{timeframe}_supertrend_{period_str}_{multiplier_str}"
            # Keep all other timeframed indicators as-is
            return field_name
        
        # DO NOT remove timeframe prefixes - they are part of the indicator key
        
        # Handle parentheses format - but this should rarely happen as resolve_field_name handles it
        # supertrend_(10,1.2) -> daily_supertrend_10_1dot2 (default to daily if no prefix)
        paren_match = re.match(r'^supertrend_\((\d+),(\d+(?:\.\d+)?)\)$', field_name)
        if paren_match:
            period = paren_match.group(1)
            multiplier = paren_match.group(2)
            # Use utility functions for proper formatting
            period_str = format_period_for_key(float(period))
            multiplier_str = format_multiplier_for_key(float(multiplier))
            # Default to daily if no timeframe specified
            return f"daily_supertrend_{period_str}_{multiplier_str}"
        
        # Handle already formatted WITHOUT timeframe prefix (legacy)
        # supertrend_10_1.2 -> daily_supertrend_10_1dot2 (add daily prefix)
        if field_name.startswith('supertrend_'):
            parts = field_name.split('_')
            if len(parts) >= 3:
                # Use utility functions for proper formatting
                period = parts[1]
                multiplier = parts[2].replace('dot', '.')
                period_str = format_period_for_key(float(period))
                multiplier_str = format_multiplier_for_key(float(multiplier))
                # Add daily prefix for unprefixed supertrend
                return f'daily_supertrend_{period_str}_{multiplier_str}'
        
        return field_name
    
    async def _check_existing_fields(self) -> Set[str]:
        """Check which fields exist in the high-speed database"""
        try:
            # Get static fields
            existing_fields = self.static_fields.copy()
            
            # Check dynamic fields in JSONB
            if high_speed_db.pool:
                async with high_speed_db.pool.acquire() as conn:
                    # Get unique indicator keys from daily_candles JSONB
                    daily_result = await conn.fetch("""
                        SELECT DISTINCT jsonb_object_keys(indicators) as indicator_key
                        FROM daily_candles
                        WHERE indicators IS NOT NULL AND indicators != '{}'
                        LIMIT 1000
                    """)
                    
                    for row in daily_result:
                        existing_fields.add(row['indicator_key'])
                    
                    # Also check weekly_candles table for weekly indicators
                    try:
                        weekly_result = await conn.fetch("""
                            SELECT DISTINCT jsonb_object_keys(indicators) as indicator_key
                            FROM weekly_candles
                            WHERE indicators IS NOT NULL AND indicators != '{}'
                            LIMIT 1000
                        """)
                        
                        for row in weekly_result:
                            existing_fields.add(row['indicator_key'])
                    except Exception as weekly_error:
                        logger.debug(f"Weekly candles table not accessible: {weekly_error}")
                    
                    # Also check monthly_candles table for monthly indicators
                    try:
                        monthly_result = await conn.fetch("""
                            SELECT DISTINCT jsonb_object_keys(indicators) as indicator_key
                            FROM monthly_candles
                            WHERE indicators IS NOT NULL AND indicators != '{}'
                            LIMIT 1000
                        """)
                        
                        for row in monthly_result:
                            existing_fields.add(row['indicator_key'])
                    except Exception as monthly_error:
                        logger.debug(f"Monthly candles table not accessible: {monthly_error}")
            
            logger.info(f"Found {len(existing_fields)} existing fields in database")
            return existing_fields
            
        except Exception as e:
            logger.error(f"Error checking existing fields: {e}")
            # Return at least static fields
            return self.static_fields.copy()
    
    async def _calculate_missing_indicators(self, missing_fields: Set[str]) -> List[Dict]:
        """Calculate missing indicators dynamically"""
        calculated = []
        
        for field in missing_fields:
            try:
                # Parse indicator from field name
                indicator_def = self._parse_indicator_from_field(field)
                if not indicator_def:
                    logger.warning(f"Cannot parse indicator from field: {field}")
                    continue
                
                logger.info(f"Calculating indicator: {indicator_def}")
                
                # Calculate indicator using dynamic indicator manager
                success = await dynamic_indicator_manager.calculate_and_store_indicator(
                    indicator_def,
                    store_in_highspeed=True
                )
                
                if success:
                    calculated.append(indicator_def)
                    logger.info(f"✅ Calculated and stored: {field}")
                else:
                    logger.warning(f"Failed to calculate: {field}")
                    
            except Exception as e:
                logger.error(f"Error calculating {field}: {e}")
        
        return calculated
    
    def _parse_indicator_from_field(self, field_name: str) -> Optional[Dict]:
        """Parse indicator definition from field name"""
        # Handle percentage change indicators: daily_pctchg, weekly_pctchg, etc.
        if 'pctchg' in field_name:
            parts = field_name.split('_')
            if len(parts) >= 2:  # e.g., daily_pctchg, weekly_pctchg
                timeframe = parts[0]  # daily, weekly, monthly
                # Validate timeframe
                if timeframe in ['daily', 'weekly', 'monthly']:
                    return {
                        "name": "PercentageChange",
                        "timeframe": timeframe,
                        "params": {}  # No parameters needed - always compare to 1 period ago
                    }
                else:
                    # Default to daily if invalid timeframe
                    return {
                        "name": "PercentageChange",
                        "timeframe": "daily",
                        "params": {}
                    }
        
        # Handle ALL timeframed SuperTrend with parameters
        # Including: daily_supertrend_10_3, weekly_supertrend_10_3, monthly_supertrend_10_3
        elif field_name.startswith(('daily_supertrend_', 'weekly_supertrend_', 'monthly_supertrend_')):
            parts = field_name.split('_')
            if len(parts) >= 4:  # timeframed supertrend with parameters
                try:
                    timeframe = parts[0]  # daily, weekly or monthly
                    period = float(parts[2])
                    multiplier_str = parts[3].replace('dot', '.')
                    multiplier = float(multiplier_str)
                    
                    return {
                        "name": "SuperTrend",
                        "timeframe": timeframe,
                        "params": {
                            "period": period,
                            "multiplier": multiplier
                        }
                    }
                except ValueError:
                    logger.error(f"Invalid {timeframe} SuperTrend parameters in {field_name}")
        
        # Handle unprefixed SuperTrend (legacy): supertrend_10_1dot2
        # This should rarely happen now, but keep for backward compatibility
        elif field_name.startswith('supertrend_'):
            parts = field_name.split('_')
            if len(parts) >= 3:
                try:
                    period = float(parts[1])
                    multiplier_str = parts[2].replace('dot', '.')
                    multiplier = float(multiplier_str)
                    
                    # Default to daily for unprefixed supertrend
                    return {
                        "name": "SuperTrend",
                        "timeframe": "daily",
                        "params": {
                            "period": period,
                            "multiplier": multiplier
                        }
                    }
                except ValueError:
                    logger.error(f"Invalid SuperTrend parameters in {field_name}")
        
        # Handle RSI with optional timeframe prefix
        elif 'rsi_' in field_name:
            parts = field_name.split('_')
            timeframe = "daily"  # default
            period_idx = 1
            
            # Check if first part is a timeframe
            if len(parts) >= 3 and parts[0] in ['daily', 'weekly', 'monthly']:
                timeframe = parts[0]
                period_idx = 2
            
            if len(parts) > period_idx:
                try:
                    period = float(parts[period_idx])
                    return {
                        "name": "RSI",
                        "timeframe": timeframe,
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle SMA with optional timeframe prefix
        elif 'sma_' in field_name:
            parts = field_name.split('_')
            timeframe = "daily"  # default
            period_idx = 1
            
            # Check if first part is a timeframe
            if len(parts) >= 3 and parts[0] in ['daily', 'weekly', 'monthly']:
                timeframe = parts[0]
                period_idx = 2
            
            if len(parts) > period_idx:
                try:
                    period = float(parts[period_idx])
                    return {
                        "name": "SMA",
                        "timeframe": timeframe,
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle EMA with optional timeframe prefix
        elif 'ema_' in field_name:
            parts = field_name.split('_')
            timeframe = "daily"  # default
            period_idx = 1
            
            # Check if first part is a timeframe
            if len(parts) >= 3 and parts[0] in ['daily', 'weekly', 'monthly']:
                timeframe = parts[0]
                period_idx = 2
            
            if len(parts) > period_idx:
                try:
                    period = float(parts[period_idx])
                    return {
                        "name": "EMA",
                        "timeframe": timeframe,
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle ATR with optional timeframe prefix
        elif 'atr_' in field_name:
            parts = field_name.split('_')
            timeframe = "daily"  # default
            period_idx = 1
            
            # Check if first part is a timeframe
            if len(parts) >= 3 and parts[0] in ['daily', 'weekly', 'monthly']:
                timeframe = parts[0]
                period_idx = 2
            
            if len(parts) > period_idx:
                try:
                    period = int(parts[period_idx])  # ATR period is typically integer
                    return {
                        "name": "atr",
                        "timeframe": timeframe,
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle Volume indicators: weekly_volume, monthly_volume
        elif field_name in ['weekly_volume', 'monthly_volume']:
            parts = field_name.split('_')
            if len(parts) == 2:
                timeframe = parts[0]  # weekly or monthly
                return {
                    "name": "Volume",
                    "timeframe": timeframe,
                    "params": {}  # No parameters needed for volume
                }
        
        # Handle daily volume (though it's usually just "volume")
        elif field_name == 'volume':
            return {
                "name": "Volume", 
                "timeframe": "daily",
                "params": {}
            }
        
        return None

# Global instance
highspeed_query_validator = HighSpeedQueryValidator()