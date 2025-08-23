import re
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

def find_previous_week_index(candles: List[Dict], current_index: int, weeks_ago: int) -> int:
    """Find the index of a candle from specified weeks ago using weekend flags."""
    if weeks_ago <= 0 or current_index < 0 or current_index >= len(candles):
        return -1
    
    weeks_found = 0
    current_candle = candles[current_index]
    
    # Check if current candle is Friday (has weekend flag)
    if current_candle.get('weekend', False):
        # If current is Friday, skip it for the count
        start_index = current_index - 1
    else:
        # If current is not Friday, include current position in search
        start_index = current_index
    
    # Start from appropriate position and go backwards
    for i in range(start_index, -1, -1):
        candle = candles[i]
        # Check if this candle has weekend flag (Friday)
        if candle.get('weekend', False):
            weeks_found += 1
            if weeks_found == weeks_ago:
                return i
    
    # If we couldn't find enough weeks, return -1
    return -1

def find_previous_month_index(candles: List[Dict], current_index: int, months_ago: int) -> int:
    """Find the index of a candle from specified months ago using monthend flags."""
    if months_ago <= 0 or current_index < 0 or current_index >= len(candles):
        return -1
    
    months_found = 0
    current_candle = candles[current_index]
    
    # Check if current candle is month end (has monthend flag)
    if current_candle.get('monthend', False):
        # If current is month end, skip it for the count
        start_index = current_index - 1
    else:
        # If current is not month end, include current position in search
        start_index = current_index
    
    # Start from appropriate position and go backwards
    for i in range(start_index, -1, -1):
        candle = candles[i]
        # Check if this candle has monthend flag
        if candle.get('monthend', False):
            months_found += 1
            if months_found == months_ago:
                return i
    
    # If we couldn't find enough months, return -1
    return -1

def get_day_of_week_name(timestamp_str: str) -> str:
    """Convert timestamp to day of week name."""
    try:
        if not timestamp_str:
            return ""
        # Handle different timestamp formats
        from datetime import datetime
        if isinstance(timestamp_str, str):
            # Try common formats
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d")
            except ValueError:
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return ""
        else:
            return ""
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[dt.weekday()]
    except Exception:
        return ""

def resolve_field_name(field_name: str) -> str:
    """Resolve field name variations to actual field names in the data."""
    import re
    
    # Handle format with spaces: "daily supertrend (10,1.2)" -> "supertrend_10_1dot2"
    # First normalize spaces to underscores
    field_name = field_name.replace(' ', '_')
    
    # Handle parentheses format: daily_supertrend_(30,1.2) -> supertrend_30_1dot2
    paren_match = re.match(r'^(daily|weekly|monthly)_supertrend_\((\d+),(\d+(?:\.\d+)?)\)$', field_name)
    if paren_match:
        timeframe = paren_match.group(1)
        period = paren_match.group(2)
        multiplier = paren_match.group(3)
        # Convert to new naming convention: remove redundant timeframe, use "dot" for decimals
        multiplier_clean = multiplier.replace('.', 'dot') if '.' in multiplier else multiplier
        return f"supertrend_{period}_{multiplier_clean}"
    
    # Handle dynamic decimal parameters for indicators
    # Check for Bollinger Bands with decimal parameters (e.g., daily_bb_upper_10_1.22)
    bb_match = re.match(r'^(daily|weekly|monthly)_bb_(upper|middle|lower)_(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)$', field_name)
    if bb_match:
        timeframe = bb_match.group(1)
        band_type = bb_match.group(2)
        period = bb_match.group(3)
        std_dev = bb_match.group(4)
        # Return in the format expected by the data: timeframe_bb_period_stddev_bandtype
        return f"{timeframe}_bb_{period}_{std_dev}_{band_type}"
    
    # Check for SuperTrend with decimal parameters (e.g., daily_supertrend_10_2.44, daily_supertrend_30_1_2)
    # Convert to new naming convention: supertrend_30_1dot2 (no redundant timeframe, use "dot" for decimals)
    st_match = re.match(r'^(daily|weekly|monthly)_supertrend_(\d+)_(\d+(?:[_\.]\d+)?)$', field_name)
    if st_match:
        timeframe = st_match.group(1)
        period = st_match.group(2)
        multiplier = st_match.group(3)
        # Convert to new naming convention: remove redundant timeframe, use "dot" for decimals
        # Handle both underscore and dot formats for the multiplier
        if '_' in multiplier and '.' not in multiplier:
            # Convert underscore format (1_2) to dot format (1dot2)
            multiplier_clean = multiplier.replace('_', 'dot')
        elif '.' in multiplier:
            # Convert dot format (1.2) to dot format (1dot2)
            multiplier_clean = multiplier.replace('.', 'dot')
        else:
            # Integer format (2)
            multiplier_clean = multiplier
        return f"supertrend_{period}_{multiplier_clean}"
    
    # Check for other indicators with decimal parameters
    ind_match = re.match(r'^(daily|weekly|monthly)_(rsi|sma|ema|pctchg)_(\d+(?:\.\d+)?)$', field_name)
    if ind_match:
        timeframe = ind_match.group(1)
        indicator = ind_match.group(2)
        period = ind_match.group(3)
        return f"{timeframe}_{indicator}_{period}"
    
    # Field name mappings for common variations
    field_mappings = {
        # Daily price fields - map to actual field names in the data (without daily_ prefix)
        'daily_close': 'close',
        'daily_open': 'open', 
        'daily_high': 'high',
        'daily_low': 'low',
        'daily_volume': 'volume',
        'daily_pctchg_1': 'daily_pctchg_1',  # Special case - precalculated indicator
        
        # Short versions already map correctly to base names
        'close': 'close',
        'open': 'open',
        'high': 'high',  
        'low': 'low',
        'volume': 'volume',
        
        # Weekly price fields (these exist as-is)
        'weekly_close': 'weekly_close',
        'weekly_open': 'weekly_open',
        'weekly_high': 'weekly_high', 
        'weekly_low': 'weekly_low',
        'weekly_volume': 'weekly_volume',
        
        # Monthly price fields (these exist as-is)
        'monthly_close': 'monthly_close',
        'monthly_open': 'monthly_open',
        'monthly_high': 'monthly_high',
        'monthly_low': 'monthly_low', 
        'monthly_volume': 'monthly_volume',
        
        # Bollinger Band fields - map from query format to actual field names
        'daily_bb_upper_20_2': 'daily_bb_20_2_upper',
        'daily_bb_middle_20_2': 'daily_bb_20_2_middle',
        'daily_bb_lower_20_2': 'daily_bb_20_2_lower',
        
        # Add more BB variations if needed
        'bb_upper_20_2': 'daily_bb_20_2_upper',
        'bb_middle_20_2': 'daily_bb_20_2_middle',
        'bb_lower_20_2': 'daily_bb_20_2_lower',
        
        # Handle SuperTrend field variations with decimal points
        'weekly_supertrend_10_2': 'weekly_supertrend_10_2.0',  # Map to actual field name in data
        'weekly_supertrend_10_2.0': 'weekly_supertrend_10_2.0'
    }
    
    # Return mapped name if exists, otherwise return original
    return field_mappings.get(field_name.lower(), field_name)

def get_field_value(candle: Dict[str, Any], field_name: str, candles: List[Dict[str, Any]] = None, candle_index: int = -1) -> Any:
    """Get field value from candle, computing special fields on the fly if needed."""
    if field_name == 'daily_pctchg_1':
        # First, try to get the precalculated value
        precalculated_value = candle.get('daily_pctchg_1')
        if precalculated_value is not None:
            return precalculated_value
        
        # If not precalculated, compute daily percentage change on the fly
        if candles is None or candle_index <= 0:
            return None
        
        current_close = candle.get('close')
        prev_close = candles[candle_index - 1].get('close')
        
        if current_close is not None and prev_close is not None and prev_close != 0:
            pct_change = ((float(current_close) - float(prev_close)) / float(prev_close)) * 100
            return pct_change
        return None
    else:
        # Regular field lookup
        return candle.get(field_name)

async def get_available_fields_from_dynamic_indicators() -> set:
    """Get available fields from dynamic indicator manager (database-based)."""
    
    try:
        # Import here to avoid circular imports
        from services.dynamic_indicator_manager import dynamic_indicator_manager
        
        # Get active indicators from dynamic indicator manager
        indicators = await dynamic_indicator_manager.get_active_indicators_list()
        
        available_fields = set()
        
        # Add basic price fields that are always available
        for field in ['open', 'high', 'low', 'close', 'volume']:
            available_fields.add(field)  # Basic fields without prefix
        
        # Weekly and monthly fields have their prefixes
        for timeframe in ['weekly', 'monthly']:
            for field in ['open', 'high', 'low', 'close', 'volume']:
                available_fields.add(f"{timeframe}_{field}")
        
        # Add indicator fields based on active indicators
        for indicator in indicators:
            timeframe = indicator.get("timeframe", "daily")
            name = indicator.get("name", "").lower()
            params = indicator.get("params", {})
            
            if name == "supertrend":
                period = params.get("period", 10)
                multiplier = params.get("multiplier", 3)
                # Generate the field name with unambiguous decimal naming, remove redundant timeframe
                period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period).replace('.', 'dot')
                multiplier_str = str(int(multiplier)) if isinstance(multiplier, float) and multiplier.is_integer() else str(multiplier).replace('.', 'dot')
                field_name = f"{name}_{period_str}_{multiplier_str}"
                available_fields.add(field_name)
                # Also add backward compatibility variants
                if isinstance(multiplier, (int, float)) and float(multiplier).is_integer():
                    # Old format compatibility
                    field_name_old = f"daily_{name}_{period_str}_{int(multiplier)}"
                    available_fields.add(field_name_old)
            elif name == "pctchg":
                period = params.get("period", 1)
                period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period)
                field_name = f"{timeframe}_{name}_{period_str}"
                available_fields.add(field_name)
            elif name == "bollingerbands" or name == "bb":
                period = params.get("period", 20)
                std_dev = params.get("std_dev", 2)
                period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period)
                std_str = str(int(std_dev)) if isinstance(std_dev, float) and std_dev.is_integer() else str(std_dev)
                # Bollinger bands have upper, middle, lower suffixes
                for suffix in ['upper', 'middle', 'lower']:
                    field_name = f"{timeframe}_bb_{period_str}_{std_str}_{suffix}"
                    available_fields.add(field_name)
            elif name in ["rsi", "sma", "ema", "adx", "atr", "cci", "macd", "stoch", "wma"]:
                # Standard indicators with single period parameter
                period = params.get("period", 14)
                period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period)
                field_name = f"{timeframe}_{name}_{period_str}"
                available_fields.add(field_name)
            elif name == "volume":
                # Volume indicator doesn't have parameters
                field_name = f"{timeframe}_{name}"
                available_fields.add(field_name)
            # Add other indicator types as needed
            
        logger.info(f"Dynamic indicator manager provided {len(available_fields)} available fields")
        return available_fields
        
    except Exception as e:
        logger.warning(f"Failed to load from dynamic indicator manager: {e}")
        return set()

def get_available_fields_from_precalculated_indicators() -> set:
    """Legacy function - now returns empty set to force async validation."""
    logger.warning("Using legacy validation method - should use async dynamic indicators")
    return set()

async def validate_query_fields(parsed_query: Dict[str, Any], sample_stock_path: str = None) -> Dict[str, Any]:
    """Validate if all fields in the query exist in precalculated data."""
    
    try:
        # Use dynamic indicator manager for field detection
        available_fields = await get_available_fields_from_dynamic_indicators()
        
        if not available_fields:
            # Fallback to sample file approach if dynamic method fails
            return validate_query_fields_fallback(parsed_query, sample_stock_path)
        
        logger.info(f"Available fields from dynamic indicators: {sorted(available_fields)}")
        
        # Extract all field names from the parsed query
        required_fields = set()
        conditions = parsed_query.get("conditions", [])
        
        # Debug: Log parsing details  
        logger.info(f"Query parsing debug:")
        logger.info(f"  Total conditions parsed: {len(conditions)}")
        for i, condition in enumerate(conditions):
            logger.info(f"  Condition {i+1}: {condition}")
        
        
        for condition in conditions:
            left = condition.get("left", {})
            right = condition.get("right", {})
            
            # Check left side field
            if left.get("type") in ["field", "indicator"]:
                field_name = left.get("field", "")
                if field_name:
                    # Resolve field name using existing mapping
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
                    logger.info(f"    Left field: {field_name} -> {resolved_name}")
            
            # Check right side field (for field references)
            if right.get("type") == "field":
                field_name = right.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
                    logger.info(f"    Right field: {field_name} -> {resolved_name}")
            
            # Check time offset fields
            if left.get("type") == "time_offset_field":
                field_name = left.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
                    logger.info(f"    Left time offset field: {field_name} -> {resolved_name}")
            
            if right.get("type") == "time_offset_field":
                field_name = right.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
                    logger.info(f"    Right time offset field: {field_name} -> {resolved_name}")
        
        # Check for missing fields, but allow computed fields
        computed_fields = set()  # Empty set for computed fields
        # Note: percentage change fields are now precalculated indicators rather than computed
        # computed_fields.add('daily_pctchg_1')  # Moved to precalculated indicators
        
        # Handle format variations (e.g., weekly_supertrend_10_2 vs weekly_supertrend_10_2.0)
        extended_available_fields = set(available_fields)
        for available_field in list(available_fields):
            # Remove .0 suffix for supertrend fields to create alternate mapping
            if '_supertrend_' in available_field and available_field.endswith('.0'):
                alt_field = available_field[:-2]  # Remove .0
                extended_available_fields.add(alt_field)
        
        available_fields_plus_computed = extended_available_fields | computed_fields
        missing_fields = required_fields - available_fields_plus_computed
        
        # Debug: Log field detection details
        logger.info(f"Field detection debug:")
        logger.info(f"  Required fields: {sorted(required_fields)}")
        logger.info(f"  Available fields: {sorted(available_fields)}")
        logger.info(f"  Extended available: {sorted(extended_available_fields)}")
        logger.info(f"  Missing fields: {sorted(missing_fields)}")
        
        
        if missing_fields:
            return {
                "valid": False,
                "error": f"Missing fields in precalculated data: {', '.join(sorted(missing_fields))}",
                "missing_fields": list(missing_fields),
                "available_fields": sorted(list(available_fields_plus_computed))
            }
        
        return {"valid": True, "required_fields": list(required_fields)}
        
    except Exception as e:
        return {"valid": False, "error": f"Validation error: {str(e)}"}

def validate_query_fields_fallback(parsed_query: Dict[str, Any], sample_stock_path: str = None) -> Dict[str, Any]:
    """Fallback validation method using sample stock file (slower but more comprehensive)."""
    import json
    from pathlib import Path
    
    # Get a sample stock file to check field availability
    if not sample_stock_path:
        # Try different possible paths
        possible_dirs = [
            Path(__file__).parent.parent / "precalculatedStorage",  # From services/ directory
            Path.cwd().parent / "precalculatedStorage",              # From python-api/ directory
            Path.cwd() / "precalculatedStorage"                     # If running from parent directory
        ]
        
        precalc_dir = None
        for dir_path in possible_dirs:
            if dir_path.exists():
                precalc_dir = dir_path
                break
        
        if not precalc_dir:
            # Create the directory if it doesn't exist
            precalc_dir = Path(__file__).parent.parent / "precalculatedStorage"
            precalc_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created precalculatedStorage directory at: {precalc_dir}")
            return {"valid": False, "error": "Precalculated storage directory was missing and has been created. Please precalculate indicators first."}
            
        sample_files = list(precalc_dir.glob("*_piped.json"))
        if not sample_files:
            return {
                "valid": False, 
                "error": "No precalculated data found. Please run 'Precalculate Indicators' first to generate the required data.",
                "hint": "Click the 'Precalculate Indicators' button in the frontend to generate data for all stocks."
            }
        sample_stock_path = str(sample_files[0])
    
    try:
        # Load sample data to check available fields
        with open(sample_stock_path, 'r') as f:
            sample_data = json.load(f)
        
        if not sample_data.get("data") or len(sample_data["data"]) == 0:
            return {"valid": False, "error": "No candle data found in sample stock"}
        
        # Get the latest candle to check available fields
        latest_candle = sample_data["data"][-1]
        available_fields = set(latest_candle.keys())
        
        # Continue with validation logic WITHOUT recursion
        # Extract all field names from the parsed query
        required_fields = set()
        conditions = parsed_query.get("conditions", [])
        
        for condition in conditions:
            left = condition.get("left", {})
            right = condition.get("right", {})
            
            # Check left side field
            if left.get("type") in ["field", "indicator"]:
                field_name = left.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
            
            # Check right side field (for field references)
            if right.get("type") == "field":
                field_name = right.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
            
            # Check time offset fields
            if left.get("type") == "time_offset_field":
                field_name = left.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
            
            if right.get("type") == "time_offset_field":
                field_name = right.get("field", "")
                if field_name:
                    resolved_name = resolve_field_name(field_name)
                    required_fields.add(resolved_name)
        
        # Check for missing fields
        missing_fields = required_fields - available_fields
        
        if missing_fields:
            return {
                "valid": False,
                "error": f"Missing fields in precalculated data: {', '.join(sorted(missing_fields))}",
                "missing_fields": list(missing_fields),
                "available_fields": sorted(list(available_fields))
            }
        
        return {"valid": True, "required_fields": list(required_fields)}
        
    except Exception as e:
        return {"valid": False, "error": f"Validation error: {str(e)}"}

def parse_right_side_expression(expression: str) -> Dict[str, Any]:
    """Parse the right side of a condition which could be a number, field, or time-offset expression."""
    expression = expression.strip()
    
    # Check if it's a time-offset expression with arithmetic like "1 day ago weekly_volume * 2"
    time_offset_arithmetic_pattern = r'(\d+)\s+(day|week|month)s?\s+ago\s+(\w+(?:_\w+)*)\s*\*\s*(\d+(?:\.\d+)?)'
    time_arithmetic_match = re.match(time_offset_arithmetic_pattern, expression)
    
    if time_arithmetic_match:
        offset_value = int(time_arithmetic_match.group(1))
        offset_unit = time_arithmetic_match.group(2)
        field_name = time_arithmetic_match.group(3).strip()
        multiplier = float(time_arithmetic_match.group(4))
        
        # Resolve field name variations
        resolved_field_name = resolve_field_name(field_name)
        
        return {
            "type": "time_offset_field_arithmetic",
            "field": resolved_field_name,
            "offset_value": offset_value,
            "offset_unit": offset_unit,
            "operation": "*",
            "operand": multiplier,
            "value": None
        }
    
    # Check if it's a simple time-offset expression like "1 day ago daily_close"
    time_offset_pattern = r'(\d+)\s+(day|week|month)s?\s+ago\s+(.+)'
    time_match = re.match(time_offset_pattern, expression)
    
    if time_match:
        offset_value = int(time_match.group(1))
        offset_unit = time_match.group(2)
        field_name = time_match.group(3).strip()
        
        # Resolve field name variations (e.g., 'daily_close' -> 'close')
        resolved_field_name = resolve_field_name(field_name)
        
        return {
            "type": "time_offset_field",
            "field": resolved_field_name,
            "offset_value": offset_value,
            "offset_unit": offset_unit,
            "value": None
        }
    
    # Check if it's a simple number
    if expression.replace('.', '').replace('-', '').isdigit():
        return {
            "type": "value",
            "field": None,
            "value": float(expression)
        }
    
    # Otherwise, it's a simple field reference
    resolved_field_name = resolve_field_name(expression)
    return {
        "type": "field",
        "field": resolved_field_name,
        "value": None
    }

def is_historical_query(parsed_query):
    """Check if the parsed query contains historical time offset conditions."""
    conditions = parsed_query.get("conditions", [])
    # Check both left and right sides for time offset fields
    for condition in conditions:
        left_type = condition.get("left", {}).get("type")
        right_type = condition.get("right", {}).get("type")
        if left_type == "time_offset_field" or right_type in ["time_offset_field", "time_offset_field_arithmetic"]:
            return True
    return False

def parse_query(query: str) -> Dict[str, Any]:
    """Parse a query string into structured conditions."""
    # This is a placeholder implementation
    # The actual implementation would need to parse complex query syntax
    # For now, return a basic structure
    
    # Enhanced regex patterns for conditions including crossed above/below
    # First try to match "crossed above" and "crossed below" patterns
    # Support both simple values and complex expressions like "1 day ago daily_close"
    # Updated to handle decimal numbers in field names (e.g., weekly_supertrend_30_1.56)
    crossed_pattern = r'([\w\.]+(?:\(\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)*\))?)\s+(crossed\s+(?:above|below))\s+(.+)'
    
    # Pattern for time-offset queries on the left side like "1 day ago daily_supertrend_10_2 > 200"
    # Updated to handle time offset expressions on both sides and decimal numbers
    time_offset_pattern = r'(\d+)\s+(day|week|month)s?\s+ago\s+([\w\.]+(?:_[\w\.]+)*(?:\(\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)*\))?)\s*([><=!]+)\s*(.+)'
    
    # Basic comparison operators - updated to handle spaces and complex right side expressions and decimal numbers
    basic_pattern = r'([\w\.\s]+(?:\(\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)*\))?)\s*([><=!]+)\s*(.+)'
    
    conditions = []
    logical_operators = []
    
    # Split by 'and' and 'or' operators
    parts = re.split(r'\s+(and|or)\s+', query.lower())
    
    for i, part in enumerate(parts):
        if part in ['and', 'or']:
            logical_operators.append(part)
        else:
            part = part.strip()
            
            # Try crossed pattern first
            crossed_match = re.match(crossed_pattern, part)
            if crossed_match:
                left_field = crossed_match.group(1)
                operator = crossed_match.group(2).replace(' ', ' ')  # "crossed above" or "crossed below"
                right_field = crossed_match.group(3)
                
                # Parse the right side expression (could be number, field, or time-offset)
                right_parsed = parse_right_side_expression(right_field)
                
                # Resolve field name for left side
                resolved_left_field = resolve_field_name(left_field)
                
                conditions.append({
                    "left": {
                        "type": "field" if '_' in left_field else "indicator",
                        "field": resolved_left_field,  # Use resolved field name
                        "name": left_field.split('_')[1] if '_' in left_field else left_field.split('(')[0]
                    },
                    "operator": operator,
                    "right": right_parsed
                })
            else:
                # Try time-offset pattern (e.g., "1 day ago daily_supertrend_10_2 > 200")
                time_offset_match = re.match(time_offset_pattern, part)
                if time_offset_match:
                    offset_value = int(time_offset_match.group(1))
                    offset_unit = time_offset_match.group(2)
                    left_field = time_offset_match.group(3)
                    operator = time_offset_match.group(4)
                    right_field = time_offset_match.group(5)
                    
                    # Parse the right side
                    right_parsed = parse_right_side_expression(right_field)
                    
                    # Resolve field name for left side
                    resolved_left_field = resolve_field_name(left_field)
                    
                    conditions.append({
                        "left": {
                            "type": "time_offset_field",
                            "field": resolved_left_field,  # Use resolved field name
                            "name": left_field.split('_')[1] if '_' in left_field else left_field.split('(')[0],
                            "offset_value": offset_value,
                            "offset_unit": offset_unit
                        },
                        "operator": operator,
                        "right": right_parsed
                    })
                else:
                    # Try basic pattern
                    basic_match = re.match(basic_pattern, part)
                    if basic_match:
                        left_field = basic_match.group(1).strip()
                        operator = basic_match.group(2)
                        right_field = basic_match.group(3)
                        
                        # Parse the right side expression (could be number, field, or time-offset)
                        right_parsed = parse_right_side_expression(right_field)
                        
                        # Convert spaces to underscores for field name resolution
                        # e.g., "daily supertrend (30,1.2)" -> "daily_supertrend_(30,1.2)"
                        field_for_resolution = left_field.replace(' ', '_')
                        
                        # Resolve field name for left side
                        resolved_left_field = resolve_field_name(field_for_resolution)
                        
                        conditions.append({
                            "left": {
                                "type": "field" if '_' in left_field else "indicator",
                                "field": resolved_left_field,  # Use resolved field name
                                "name": left_field.split('_')[1] if '_' in left_field else left_field.split('(')[0]
                            },
                            "operator": operator,
                            "right": right_parsed
                        })
    
    return {
        "conditions": conditions,
        "logicalOperators": logical_operators
    }

def find_matching_candles(candles: List[Dict[str, Any]], parsed_query: Dict[str, Any], stock: str) -> List[Dict[str, Any]]:
    """Find candles that match the query conditions."""
    matches = []
    
    try:
        conditions = parsed_query.get("conditions", [])
        logical_operators = parsed_query.get("logicalOperators", [])
        
        # For all queries, we should iterate through all candles and evaluate conditions
        # The presence of time-offset conditions doesn't change this fundamental approach
        for i, candle in enumerate(candles):
            try:
                results = []
                
                # Evaluate each condition
                for condition in conditions:
                    left = condition["left"]
                    operator = condition["operator"]
                    right = condition["right"]
                    
                    # Get left value
                    left_value = None
                    left_field_name = None
                    if left["type"] == "field":
                        left_field_name = left["field"]
                        raw_left_value = get_field_value(candle, left_field_name, candles, i)
                        # Skip if indicator value is None (insufficient data)
                        if raw_left_value is None:
                            left_value = None
                        else:
                            left_value = float(raw_left_value)
                    elif left["type"] == "indicator":
                        # Handle indicator values
                        left_field_name = left["name"]
                        raw_left_value = candle.get(left_field_name)
                        # Skip if indicator value is None (insufficient data)
                        if raw_left_value is None:
                            left_value = None
                        else:
                            left_value = float(raw_left_value)
                    elif left["type"] == "time_offset_field":
                        # Handle left-side time offset conditions like "1 day ago daily_volume > 10000"
                        offset_val = left.get("offset_value", 0)
                        offset_unit = left.get("offset_unit", "day")
                        field_name = left["field"]
                        
                        # Calculate target index for historical candle
                        if offset_unit == "day":
                            historical_index = i - offset_val
                        elif offset_unit == "week":
                            historical_index = find_previous_week_index(candles, i, offset_val)
                        elif offset_unit == "month":
                            historical_index = find_previous_month_index(candles, i, offset_val)
                        else:
                            historical_index = -1
                        
                        if historical_index >= 0 and historical_index < len(candles):
                            historical_candle = candles[historical_index]
                            raw_left_value = get_field_value(historical_candle, field_name, candles, historical_index)
                            if raw_left_value is not None:
                                left_value = float(raw_left_value)
                    
                    # Get right value
                    right_value = None
                    if right["type"] == "value":
                        right_value = right["value"]
                    elif right["type"] == "field":
                        raw_right_value = get_field_value(candle, right["field"], candles, i)
                        # Skip if indicator value is None (insufficient data)
                        if raw_right_value is None:
                            right_value = None
                        else:
                            right_value = float(raw_right_value)
                    elif right["type"] == "time_offset_field":
                        # Handle time offset expressions like "1 day ago daily_close"
                        offset_value = right["offset_value"]
                        offset_unit = right["offset_unit"]
                        field_name = right["field"]
                        
                        # Calculate the offset index based on unit
                        if offset_unit == "day":
                            offset_index = i - offset_value
                        elif offset_unit == "week":
                            # For weekly offset, find the Friday from that many weeks ago
                            offset_index = find_previous_week_index(candles, i, offset_value)
                        elif offset_unit == "month":
                            # For monthly offset, find the monthend from that many months ago
                            offset_index = find_previous_month_index(candles, i, offset_value)
                        else:
                            offset_index = -1  # Invalid
                        
                        # Check if the offset index is valid and get the historical value
                        if offset_index >= 0 and offset_index < len(candles):
                            historical_candle = candles[offset_index]
                            raw_right_value = get_field_value(historical_candle, field_name, candles, offset_index)
                            if raw_right_value is None:
                                right_value = None
                            else:
                                right_value = float(raw_right_value)
                        else:
                            right_value = None  # Not enough historical data
                    elif right["type"] == "time_offset_field_arithmetic":
                        # Handle arithmetic operations on time offset fields
                        offset_value = right["offset_value"]
                        offset_unit = right["offset_unit"]
                        field_name = right["field"]
                        operation = right["operation"]
                        operand = right["operand"]
                        
                        # Calculate the offset index based on unit
                        if offset_unit == "day":
                            offset_index = i - offset_value
                        elif offset_unit == "week":
                            # For weekly offset, find the Friday from that many weeks ago
                            offset_index = find_previous_week_index(candles, i, offset_value)
                        elif offset_unit == "month":
                            # For monthly offset, find the monthend from that many months ago
                            offset_index = find_previous_month_index(candles, i, offset_value)
                        else:
                            offset_index = -1  # Invalid
                        
                        # Check if the offset index is valid and get the historical value
                        if offset_index >= 0 and offset_index < len(candles):
                            historical_candle = candles[offset_index]
                            raw_right_value = get_field_value(historical_candle, field_name, candles, offset_index)
                            if raw_right_value is not None:
                                base_value = float(raw_right_value)
                                # Apply arithmetic operation
                                if operation == "*":
                                    right_value = base_value * operand
                                else:
                                    right_value = None
                            else:
                                right_value = None
                        else:
                            right_value = None  # Not enough historical data
                    else:
                        # Unknown right type
                        right_value = None
                    
                    # Evaluate condition
                    if left_value is not None and right_value is not None:
                        if operator == "crossed above":
                            # For crossed above: current value > threshold AND previous value <= threshold
                            result = False
                            
                            # Determine if we need weekly/monthly comparison
                            is_weekly_field = left_field_name and 'weekly' in left_field_name
                            is_monthly_field = left_field_name and 'monthly' in left_field_name
                            
                            if is_weekly_field:
                                # For weekly fields, find the previous week
                                prev_week_idx = find_previous_week_index(candles, i, 1)
                                if prev_week_idx >= 0:
                                    prev_candle = candles[prev_week_idx]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, prev_week_idx)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # For weekly comparison, also get the right value from previous week
                                        if right["type"] == "field" and 'weekly' in right.get("field", ""):
                                            prev_right_raw = get_field_value(prev_candle, right["field"], candles, prev_week_idx)
                                            if prev_right_raw is not None:
                                                prev_right_value = float(prev_right_raw)
                                                # Previous week: left <= right, Current week: left > right
                                                result = (left_value > right_value) and (prev_left_value <= prev_right_value)
                                        else:
                                            # Static right value
                                            result = (left_value > right_value) and (prev_left_value <= right_value)
                            elif is_monthly_field:
                                # For monthly fields, find the previous month
                                prev_month_idx = find_previous_month_index(candles, i, 1)
                                if prev_month_idx >= 0:
                                    prev_candle = candles[prev_month_idx]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, prev_month_idx)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # For monthly comparison, also get the right value from previous month
                                        if right["type"] == "field" and 'monthly' in right.get("field", ""):
                                            prev_right_raw = get_field_value(prev_candle, right["field"], candles, prev_month_idx)
                                            if prev_right_raw is not None:
                                                prev_right_value = float(prev_right_raw)
                                                # Previous month: left <= right, Current month: left > right
                                                result = (left_value > right_value) and (prev_left_value <= prev_right_value)
                                        else:
                                            # Static right value
                                            result = (left_value > right_value) and (prev_left_value <= right_value)
                            else:
                                # Daily comparison - use previous candle
                                if i > 0 and left_field_name:
                                    prev_candle = candles[i-1]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, i-1)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        result = (left_value > right_value) and (prev_left_value <= right_value)
                        elif operator == "crossed below":
                            # For crossed below: current value < threshold AND previous value >= threshold
                            result = False
                            
                            # Determine if we need weekly/monthly comparison
                            is_weekly_field = left_field_name and 'weekly' in left_field_name
                            is_monthly_field = left_field_name and 'monthly' in left_field_name
                            
                            if is_weekly_field:
                                # For weekly fields, find the previous week
                                prev_week_idx = find_previous_week_index(candles, i, 1)
                                if prev_week_idx >= 0:
                                    prev_candle = candles[prev_week_idx]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, prev_week_idx)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # For weekly comparison, also get the right value from previous week
                                        if right["type"] == "field" and 'weekly' in right.get("field", ""):
                                            prev_right_raw = get_field_value(prev_candle, right["field"], candles, prev_week_idx)
                                            if prev_right_raw is not None:
                                                prev_right_value = float(prev_right_raw)
                                                # Previous week: left >= right, Current week: left < right
                                                result = (left_value < right_value) and (prev_left_value >= prev_right_value)
                                        else:
                                            # Static right value
                                            result = (left_value < right_value) and (prev_left_value >= right_value)
                            elif is_monthly_field:
                                # For monthly fields, find the previous month
                                prev_month_idx = find_previous_month_index(candles, i, 1)
                                if prev_month_idx >= 0:
                                    prev_candle = candles[prev_month_idx]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, prev_month_idx)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # For monthly comparison, also get the right value from previous month
                                        if right["type"] == "field" and 'monthly' in right.get("field", ""):
                                            prev_right_raw = get_field_value(prev_candle, right["field"], candles, prev_month_idx)
                                            if prev_right_raw is not None:
                                                prev_right_value = float(prev_right_raw)
                                                # Previous month: left >= right, Current month: left < right
                                                result = (left_value < right_value) and (prev_left_value >= prev_right_value)
                                        else:
                                            # Static right value
                                            result = (left_value < right_value) and (prev_left_value >= right_value)
                            else:
                                # Daily comparison - use previous candle
                                if i > 0 and left_field_name:
                                    prev_candle = candles[i-1]
                                    prev_raw_value = get_field_value(prev_candle, left_field_name, candles, i-1)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        result = (left_value < right_value) and (prev_left_value >= right_value)
                        elif operator == ">":
                            result = left_value > right_value
                        elif operator == "<":
                            result = left_value < right_value
                        elif operator == ">=":
                            result = left_value >= right_value
                        elif operator == "<=":
                            result = left_value <= right_value
                        elif operator == "==":
                            result = left_value == right_value
                        elif operator == "!=":
                            result = left_value != right_value
                        else:
                            result = False
                        
                        results.append(result)
                    else:
                        results.append(False)
                    
                # Combine results with logical operators
                if len(results) == 1:
                    final_result = results[0]
                else:
                    final_result = results[0]
                    for j, logical_op in enumerate(logical_operators):
                        if j + 1 < len(results):
                            if logical_op == "and":
                                final_result = final_result and results[j + 1]
                            elif logical_op == "or":
                                final_result = final_result or results[j + 1]
                
                if final_result:
                    matches.append({
                        "stock": stock,
                        "date": candle.get("timestamp", ""),
                        "day": candle.get("day", ""),
                        "open": candle.get("open", ""),
                        "high": candle.get("high", ""),
                        "low": candle.get("low", ""),
                        "close": candle.get("close", ""),
                        "volume": candle.get("volume", ""),
                        # Include any additional indicator values
                        **{k: v for k, v in candle.items() if k not in ["date", "day", "open", "high", "low", "close", "volume"]}
                    })
                    
            except Exception as e:
                logger.warning(f"Error processing candle for {stock}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error in find_matching_candles for {stock}: {e}")
    
    return matches

def get_query_examples() -> List[Dict[str, Any]]:
    """Get example queries."""
    return [
        {
            "title": "RSI Overbought",
            "query": "rsi(14) > 70",
            "description": "Find stocks where RSI is above 70 (overbought)"
        },
        {
            "title": "RSI Oversold",
            "query": "rsi(14) < 30",
            "description": "Find stocks where RSI is below 30 (oversold)"
        },
        {
            "title": "Price above SMA",
            "query": "close > sma(20)",
            "description": "Find stocks trading above 20-day simple moving average"
        },
        {
            "title": "Golden Cross",
            "query": "sma(50) > sma(200)",
            "description": "Find stocks where 50-day SMA crossed above 200-day SMA"
        },
        {
            "title": "High Volume",
            "query": "volume > sma(volume, 20) * 2",
            "description": "Find stocks with volume 2x above average"
        },
        {
            "title": "Bullish Setup",
            "query": "rsi(14) > 50 and close > sma(20) and volume > sma(volume, 10)",
            "description": "Find stocks with bullish technical setup"
        }
    ]

def detect_missing_indicators_from_fields(missing_fields: List[str]) -> List[Dict[str, Any]]:
    """Convert missing field names to indicator configurations."""
    import re
    indicators = []
    
    for field in missing_fields:
        # Use regex to properly parse decimal parameters
        # Pattern for SuperTrend: timeframe_supertrend_period_multiplier (accepts both dots and underscores)
        st_match = re.match(r'^(daily|weekly|monthly)_supertrend_(\d+(?:[_\.]\d+)?)_(\d+(?:[_\.]\d+)?)$', field)
        if st_match:
            # Convert underscores back to dots for numeric conversion
            period_str = st_match.group(2).replace('_', '.')
            multiplier_str = st_match.group(3).replace('_', '.')
            indicators.append({
                "timeframe": st_match.group(1),
                "name": "supertrend",
                "params": {
                    "period": float(period_str),
                    "multiplier": float(multiplier_str)
                }
            })
            continue
            
        # Pattern for Bollinger Bands: timeframe_bb_bandtype_period_stddev
        bb_match = re.match(r'^(daily|weekly|monthly)_bb_(upper|middle|lower)_(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)$', field)
        if bb_match:
            indicators.append({
                "timeframe": bb_match.group(1),
                "name": "bb",
                "params": {
                    "period": float(bb_match.group(3)),
                    "stdDev": float(bb_match.group(4))
                }
            })
            continue
            
        # Pattern for standard indicators: timeframe_indicator_period
        ind_match = re.match(r'^(daily|weekly|monthly)_(rsi|sma|ema|pctchg|volume)_(\d+(?:\.\d+)?)$', field)
        if ind_match:
            indicators.append({
                "timeframe": ind_match.group(1),
                "name": ind_match.group(2),
                "params": {
                    "period": float(ind_match.group(3))
                }
            })
            continue
            
        # Fallback to old parsing method for backwards compatibility
        parts = field.split('_')
        
        if len(parts) >= 3:
            timeframe = parts[0]  # daily, weekly, monthly
            indicator_name = parts[1]  # rsi, sma, supertrend, etc.
            
            # Extract parameters based on indicator type
            if indicator_name == "supertrend" and len(parts) >= 4:
                try:
                    period = float(parts[2])
                    multiplier = float(parts[3])
                    indicators.append({
                        "timeframe": timeframe,
                        "name": indicator_name,
                        "params": {
                            "period": period,
                            "multiplier": multiplier
                        }
                    })
                except (ValueError, IndexError):
                    continue
                    
            elif indicator_name == "bb" and len(parts) >= 4:  # Bollinger Bands
                try:
                    period = float(parts[2])
                    std_dev = float(parts[3])
                    indicators.append({
                        "timeframe": timeframe,
                        "name": indicator_name,
                        "params": {
                            "period": period,
                            "stdDev": std_dev
                        }
                    })
                except (ValueError, IndexError):
                    continue
                    
            elif indicator_name in ['pctchg', 'volume'] and len(parts) >= 3:
                # Percentage change or volume (may have period or be standalone)
                try:
                    if len(parts) >= 3 and parts[2].replace('.', '').isdigit():
                        period = float(parts[2])
                        indicators.append({
                            "timeframe": timeframe,
                            "name": indicator_name,
                            "params": {
                                "period": period
                            }
                        })
                    else:
                        # Volume without period
                        indicators.append({
                            "timeframe": timeframe,
                            "name": indicator_name,
                            "params": {}
                        })
                except (ValueError, IndexError):
                    continue
            else:
                # Standard indicators with just period (rsi, sma, ema, etc.)
                try:
                    period = float(parts[2])
                    indicators.append({
                        "timeframe": timeframe,
                        "name": indicator_name,
                        "params": {
                            "period": period
                        }
                    })
                except (ValueError, IndexError):
                    continue
    
    return indicators

def extract_indicators_from_query(parsed_query: Dict[str, Any]) -> Dict[str, Any]:
    """Extract required indicators and timeframes from parsed query."""
    indicators = []
    timeframes = ["daily"]  # Default timeframe
    
    try:
        conditions = parsed_query.get("conditions", [])
        
        for condition in conditions:
            left = condition["left"]
            right = condition["right"]
            
            # Check left side
            if left["type"] == "indicator" and "name" in left:
                indicator_name = left["name"]
                # Extract period from field like "rsi(14)"
                period = 14  # default
                field = left.get("field", "")
                if "(" in field and ")" in field:
                    try:
                        period_match = re.search(r'\(([0-9.]+)\)', field)
                        if period_match:
                            period = float(period_match.group(1))
                    except:
                        period = 14
                
                indicators.append({
                    "name": indicator_name,
                    "period": period,
                    "params": {"period": period}
                })
            
            # Check right side
            if right["type"] == "indicator" and "name" in right:
                indicator_name = right["name"]
                period = 14  # default
                field = right.get("field", "")
                if "(" in field and ")" in field:
                    try:
                        period_match = re.search(r'\(([0-9.]+)\)', field)
                        if period_match:
                            period = float(period_match.group(1))
                    except:
                        period = 14
                
                indicators.append({
                    "name": indicator_name,
                    "period": period,
                    "params": {"period": period}
                })
        
        # Remove duplicates
        unique_indicators = []
        seen = set()
        for indicator in indicators:
            key = f"{indicator['name']}_{indicator['period']}"
            if key not in seen:
                unique_indicators.append(indicator)
                seen.add(key)
        
    except Exception as e:
        logger.error(f"Error extracting indicators: {e}")
        unique_indicators = []
    
    return {
        "indicators": unique_indicators,
        "timeframes": timeframes
    }

async def process_stocks_with_indicators(config: Dict[str, Any], stocks: List[str]):
    """Process stocks with indicators - placeholder implementation."""
    try:
        indicators = config.get("indicators", [])
        timeframes = config.get("timeframes", ["daily"])
        
        logger.info(f"Processing {len(stocks)} stocks with {len(indicators)} indicators")
        
        # This would implement the actual indicator calculation logic
        # For now, just log the action
        for stock in stocks:
            logger.debug(f"Processing indicators for {stock}")
        
        logger.info("Indicator processing completed")
        
    except Exception as e:
        logger.error(f"Error processing stocks with indicators: {e}")
        raise