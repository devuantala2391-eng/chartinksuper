import re
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

def parse_query(query: str) -> Dict[str, Any]:
    """Parse a query string into structured conditions."""
    # This is a placeholder implementation
    # The actual implementation would need to parse complex query syntax
    # For now, return a basic structure
    
    # Enhanced regex patterns for conditions including crossed above/below
    # First try to match "crossed above" and "crossed below" patterns
    crossed_pattern = r'(\w+(?:\(\d+(?:,\d+)*\))?)\s+(crossed\s+(?:above|below))\s+(\w+(?:\(\d+(?:,\d+)*\))?|\d+\.?\d*)'
    # Basic comparison operators
    basic_pattern = r'(\w+(?:\(\d+(?:,\d+)*\))?)\s*([><=!]+)\s*(\w+(?:\(\d+(?:,\d+)*\))?|\d+\.?\d*)'
    
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
                
                conditions.append({
                    "left": {
                        "type": "field" if '_' in left_field else "indicator",
                        "field": left_field,
                        "name": left_field.split('_')[1] if '_' in left_field else left_field.split('(')[0]
                    },
                    "operator": operator,
                    "right": {
                        "type": "field" if not right_field.replace('.', '').replace('-', '').isdigit() else "value",
                        "field": right_field if not right_field.replace('.', '').replace('-', '').isdigit() else None,
                        "value": float(right_field) if right_field.replace('.', '').replace('-', '').isdigit() else None
                    }
                })
            else:
                # Try basic pattern
                basic_match = re.match(basic_pattern, part)
                if basic_match:
                    left_field = basic_match.group(1)
                    operator = basic_match.group(2)
                    right_field = basic_match.group(3)
                    
                    conditions.append({
                        "left": {
                            "type": "field" if '_' in left_field else "indicator",
                            "field": left_field,
                            "name": left_field.split('_')[1] if '_' in left_field else left_field.split('(')[0]
                        },
                        "operator": operator,
                        "right": {
                            "type": "field" if not right_field.replace('.', '').replace('-', '').isdigit() else "value",
                            "field": right_field if not right_field.replace('.', '').replace('-', '').isdigit() else None,
                            "value": float(right_field) if right_field.replace('.', '').replace('-', '').isdigit() else None
                        }
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
                    for i, logical_op in enumerate(logical_operators):
                        if i + 1 < len(results):
                            if logical_op == "and":
                                final_result = final_result and results[i + 1]
                            elif logical_op == "or":
                                final_result = final_result or results[i + 1]
                
                if final_result:
                    matches.append({
                        "stock": stock,
                        "date": candle.get("date", ""),
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