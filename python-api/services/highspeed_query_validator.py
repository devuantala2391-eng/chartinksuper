"""
High-Speed Query Validator with Dynamic Indicator Support
Validates queries against high-speed database and triggers dynamic calculation when needed
"""

import asyncio
import asyncpg
import logging
from typing import Dict, List, Set, Any, Optional
from services.dynamic_indicator_manager import dynamic_indicator_manager
from services.high_speed_database_service import high_speed_db
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
            
            # Try to calculate missing indicators dynamically
            calculated = await self._calculate_missing_indicators(missing_fields)
            
            if calculated:
                logger.info(f"Successfully calculated {len(calculated)} indicators")
                return {
                    "valid": True,
                    "required_fields": list(required_fields),
                    "calculated_indicators": calculated,
                    "message": f"Calculated {len(calculated)} missing indicators"
                }
            else:
                return {
                    "valid": False,
                    "error": f"Cannot calculate indicators: {', '.join(missing_fields)}",
                    "missing_fields": list(missing_fields),
                    "available_fields": list(existing_fields)
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
        # e.g., "daily supertrend (10,1.2)" -> "supertrend_10_1dot2"
        # e.g., "weekly_supertrend_10_2" -> "weekly_supertrend_10_2"
        
        # Handle percentage change indicators: daily_pctchg_1, weekly_pctchg_1, etc.
        if 'pctchg' in field_name:
            return field_name  # Keep as is, these are stored as calculated fields
        
        # Handle weekly/monthly SuperTrend - keep timeframe prefix
        if field_name.startswith(('weekly_', 'monthly_')):
            if 'supertrend_' in field_name:
                parts = field_name.split('_')
                if len(parts) >= 4:  # weekly_supertrend_10_2
                    # Replace dots with 'dot' in the multiplier if present
                    parts[-1] = parts[-1].replace('.', 'dot')
                    return '_'.join(parts)
            return field_name
        
        # Remove "daily_" prefix for daily indicators
        field_name = re.sub(r'^daily_', '', field_name)
        
        # Handle parentheses format: supertrend_(10,1.2) -> supertrend_10_1dot2
        paren_match = re.match(r'^supertrend_\((\d+),(\d+(?:\.\d+)?)\)$', field_name)
        if paren_match:
            period = paren_match.group(1)
            multiplier = paren_match.group(2)
            multiplier_clean = multiplier.replace('.', 'dot')
            return f"supertrend_{period}_{multiplier_clean}"
        
        # Handle already formatted: supertrend_10_1.2 -> supertrend_10_1dot2
        if 'supertrend_' in field_name:
            parts = field_name.split('_')
            if len(parts) >= 3:
                # Replace dots with 'dot' in the multiplier
                parts[-1] = parts[-1].replace('.', 'dot')
                return '_'.join(parts)
        
        return field_name
    
    async def _check_existing_fields(self) -> Set[str]:
        """Check which fields exist in the high-speed database"""
        try:
            # Get static fields
            existing_fields = self.static_fields.copy()
            
            # Check dynamic fields in JSONB
            if high_speed_db.pool:
                async with high_speed_db.pool.acquire() as conn:
                    # Get unique indicator keys from JSONB
                    result = await conn.fetch("""
                        SELECT DISTINCT jsonb_object_keys(indicators) as indicator_key
                        FROM daily_candles
                        WHERE indicators IS NOT NULL AND indicators != '{}'
                        LIMIT 1000
                    """)
                    
                    for row in result:
                        existing_fields.add(row['indicator_key'])
            
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
            if len(parts) == 2:  # e.g., daily_pctchg, weekly_pctchg
                timeframe = parts[0]  # daily, weekly, monthly
                return {
                    "name": "PercentageChange",
                    "timeframe": timeframe,
                    "params": {}  # No parameters needed - always compare to 1 period ago
                }
            elif len(parts) >= 3:  # Legacy format: daily_pctchg_1 - convert to new format
                try:
                    timeframe = parts[0]  # daily, weekly, monthly
                    # Ignore the lookback parameter, always use 1
                    return {
                        "name": "PercentageChange", 
                        "timeframe": timeframe,
                        "params": {}  # No parameters needed
                    }
                except (ValueError, IndexError):
                    logger.error(f"Invalid percentage change parameters in {field_name}")
        
        # Handle weekly/monthly SuperTrend: weekly_supertrend_10_2
        elif field_name.startswith(('weekly_supertrend_', 'monthly_supertrend_')):
            parts = field_name.split('_')
            if len(parts) >= 4:  # weekly_supertrend_10_2
                try:
                    timeframe = parts[0]  # weekly or monthly
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
                    logger.error(f"Invalid weekly/monthly SuperTrend parameters in {field_name}")
        
        # Handle daily SuperTrend: supertrend_10_1dot2
        elif field_name.startswith('supertrend_'):
            parts = field_name.split('_')
            if len(parts) >= 3:
                try:
                    period = float(parts[1])
                    multiplier_str = parts[2].replace('dot', '.')
                    multiplier = float(multiplier_str)
                    
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
        
        # Handle RSI: rsi_14
        elif field_name.startswith('rsi_'):
            parts = field_name.split('_')
            if len(parts) >= 2:
                try:
                    period = float(parts[1])
                    return {
                        "name": "RSI",
                        "timeframe": "daily",
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle SMA: sma_20
        elif field_name.startswith('sma_'):
            parts = field_name.split('_')
            if len(parts) >= 2:
                try:
                    period = float(parts[1])
                    return {
                        "name": "SMA",
                        "timeframe": "daily",
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        # Handle EMA: ema_12
        elif field_name.startswith('ema_'):
            parts = field_name.split('_')
            if len(parts) >= 2:
                try:
                    period = float(parts[1])
                    return {
                        "name": "EMA",
                        "timeframe": "daily",
                        "params": {"period": period}
                    }
                except ValueError:
                    pass
        
        return None

# Global instance
highspeed_query_validator = HighSpeedQueryValidator()