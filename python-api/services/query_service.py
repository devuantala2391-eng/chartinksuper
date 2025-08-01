import re
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

def find_previous_week_index(candles: List[Dict], current_index: int, weeks_ago: int) -> int:
    """Find the index of a candle from specified weeks ago using weekend flags."""
    if weeks_ago <= 0 or current_index < 0:
        return -1
    
    weeks_found = 0
    
    # Start from current position and go backwards
    for i in range(current_index - 1, -1, -1):
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
    if months_ago <= 0 or current_index < 0:
        return -1
    
    months_found = 0
    
    # Start from current position and go backwards
    for i in range(current_index - 1, -1, -1):
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
    # Field name mappings for common variations
    field_mappings = {
        # Daily price fields
        'daily_close': 'close',
        'daily_open': 'open', 
        'daily_high': 'high',
        'daily_low': 'low',
        'daily_volume': 'volume',
        
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
        'monthly_volume': 'monthly_volume'
    }
    
    # Return mapped name if exists, otherwise return original
    return field_mappings.get(field_name.lower(), field_name)

def parse_right_side_expression(expression: str) -> Dict[str, Any]:
    """Parse the right side of a condition which could be a number, field, or time-offset expression."""
    expression = expression.strip()
    
    # Check if it's a time-offset expression like "1 day ago daily_close"
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
        if left_type == "time_offset_field" or right_type == "time_offset_field":
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
    crossed_pattern = r'(\w+(?:\(\d+(?:,\d+)*\))?)\s+(crossed\s+(?:above|below))\s+(.+)'
    
    # Pattern for time-offset queries on the left side like "1 day ago daily_supertrend_10_2 > 200"
    time_offset_pattern = r'(\d+)\s+(day|week|month)s?\s+ago\s+(\w+(?:\(\d+(?:,\d+)*\))?)\s*([><=!]+)\s*(\w+(?:\(\d+(?:,\d+)*\))?|\d+\.?\d*)'
    
    # Basic comparison operators - updated to handle complex right side expressions
    basic_pattern = r'(\w+(?:\(\d+(?:,\d+)*\))?)\s*([><=!]+)\s*(.+)'
    
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
                        left_field = basic_match.group(1)
                        operator = basic_match.group(2)
                        right_field = basic_match.group(3)
                        
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
        
        # Check if this is a historical query (has time_offset_field on left side ONLY)
        # Right-side time offsets should use the normal evaluation path
        has_left_time_offset = any(
            condition.get("left", {}).get("type") == "time_offset_field" 
            for condition in conditions
        )
        
        if has_left_time_offset:
            # For time-offset queries like "1 day ago volume > 10000", 
            # we evaluate the condition on the historical data but return the current/latest candle as match
            
            # Find the most recent candle (current day)
            if not candles:
                return matches
                
            current_candle = candles[-1]  # Latest candle (today)
            i = len(candles) - 1  # Index of current candle
                
            # Process the current candle but evaluate conditions on historical data
            try:
                results = []
                
                # Evaluate each condition
                for condition in conditions:
                    left = condition["left"]
                    operator = condition["operator"]
                    right = condition["right"]
                    
                    # Get left value (for time-offset fields, get from historical candle)
                    left_value = None
                    if left["type"] == "time_offset_field":
                        # Find the historical candle based on offset
                        offset_val = left.get("offset_value", 0)
                        offset_unit = left.get("offset_unit", "day")
                        field_name = left["field"]
                        
                        # Calculate target index for historical candle
                        # For trading days: 1 day ago = 1 candle ago (simple array offset)
                        historical_index = i - offset_val
                        
                        if historical_index >= 0 and historical_index < len(candles):
                            historical_candle = candles[historical_index]
                            raw_left_value = historical_candle.get(field_name)
                            if raw_left_value is not None:
                                left_value = float(raw_left_value)
                    else:
                        # Handle normal field/indicator types on current candle
                        if left["type"] == "field":
                            raw_left_value = current_candle.get(left["field"])
                            if raw_left_value is not None:
                                left_value = float(raw_left_value)
                        elif left["type"] == "indicator":
                            raw_left_value = current_candle.get(left["name"])
                            if raw_left_value is not None:
                                left_value = float(raw_left_value)
                        
                    # Get right value
                    right_value = None
                    if right["type"] == "value":
                        right_value = right["value"]
                    elif right["type"] == "field":
                        raw_right_value = current_candle.get(right["field"])
                        if raw_right_value is not None:
                            right_value = float(raw_right_value)
                    elif right["type"] == "time_offset_field":
                        # Handle right-side time offsets
                        offset_value = right["offset_value"]
                        offset_unit = right["offset_unit"]
                        field_name = right["field"]
                        
                        if offset_unit == "day":
                            offset_index = i - offset_value
                        elif offset_unit == "week":
                            # For weekly offset, find the Friday from that many weeks ago
                            offset_index = find_previous_week_index(candles, i, offset_value)
                        elif offset_unit == "month":
                            # For monthly offset, find the monthend from that many months ago
                            offset_index = find_previous_month_index(candles, i, offset_value)
                        else:
                            offset_index = -1
                        
                        if offset_index >= 0 and offset_index < len(candles):
                            historical_candle = candles[offset_index]
                            raw_right_value = historical_candle.get(field_name)
                            if raw_right_value is not None:
                                right_value = float(raw_right_value)
                    
                    # Evaluate condition (moved out of time_offset_field block)
                    if left_value is not None and right_value is not None:
                        if operator == ">":
                            results.append(left_value > right_value)
                        elif operator == "<":
                            results.append(left_value < right_value)
                        elif operator == ">=":
                            results.append(left_value >= right_value)
                        elif operator == "<=":
                            results.append(left_value <= right_value)
                        elif operator == "==":
                            results.append(left_value == right_value)
                        elif operator == "!=":
                            results.append(left_value != right_value)
                        else:
                            results.append(False)
                    else:
                        results.append(False)
                    
                # Apply logical operators (simplified AND logic for now)
                if all(results):
                    matches.append({
                        "stock": stock,
                        "date": current_candle.get("timestamp", ""),
                        "dayOfWeek": get_day_of_week_name(current_candle.get("timestamp", "")),
                        "data": current_candle
                    })
                
            except Exception as e:
                # Skip this candle if evaluation fails
                pass
        else:
            # Original logic for non-historical queries
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
                            raw_left_value = candle.get(left_field_name)
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
                        
                        # Get right value
                        right_value = None
                        if right["type"] == "value":
                            right_value = right["value"]
                        elif right["type"] == "field":
                            raw_right_value = candle.get(right["field"])
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
                                raw_right_value = historical_candle.get(field_name)
                                if raw_right_value is None:
                                    right_value = None
                                else:
                                    right_value = float(raw_right_value)
                            else:
                                right_value = None  # Not enough historical data
                        
                        # Evaluate condition
                        if left_value is not None and right_value is not None:
                            if operator == "crossed above":
                                # For crossed above: current value > threshold AND previous value <= threshold
                                result = False
                                if i > 0 and left_field_name:  # Need previous candle for comparison
                                    prev_candle = candles[i-1]
                                    prev_raw_value = prev_candle.get(left_field_name)
                                    # Skip if previous value is None (insufficient data)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # Current above threshold AND previous was at or below threshold
                                        result = (left_value > right_value) and (prev_left_value <= right_value)
                            elif operator == "crossed below":
                                # For crossed below: current value < threshold AND previous value >= threshold
                                result = False
                                if i > 0 and left_field_name:  # Need previous candle for comparison
                                    prev_candle = candles[i-1]
                                    prev_raw_value = prev_candle.get(left_field_name)
                                    # Skip if previous value is None (insufficient data)
                                    if prev_raw_value is not None:
                                        prev_left_value = float(prev_raw_value)
                                        # Current below threshold AND previous was at or above threshold
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
                        period_match = re.search(r'\((\d+)\)', field)
                        if period_match:
                            period = int(period_match.group(1))
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
                        period_match = re.search(r'\((\d+)\)', field)
                        if period_match:
                            period = int(period_match.group(1))
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