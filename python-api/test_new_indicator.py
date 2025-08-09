import asyncio
import json
from pathlib import Path
import sys
sys.path.append('.')

from services.query_service import parse_query, validate_query_fields, detect_missing_indicators_from_fields

async def test_new_indicator_detection():
    """Test detection of new indicators with different parameters."""
    
    # Test query with a new parameter for supertrend
    test_query = "daily_supertrend_7_3 > 100"
    
    print(f"Testing query: {test_query}")
    print("-" * 50)
    
    # Parse the query
    parsed_query = parse_query(test_query)
    print(f"Parsed query: {json.dumps(parsed_query, indent=2)}")
    print("-" * 50)
    
    # Validate and detect missing fields
    validation_result = validate_query_fields(parsed_query)
    print(f"Validation result: {json.dumps(validation_result, indent=2)}")
    print("-" * 50)
    
    if not validation_result["valid"]:
        missing_fields = validation_result.get("missing_fields", [])
        print(f"Missing fields detected: {missing_fields}")
        
        # Convert to indicator configurations
        missing_indicators = detect_missing_indicators_from_fields(missing_fields)
        print(f"Missing indicators to add: {json.dumps(missing_indicators, indent=2)}")
        
        # Check what's currently in precalculatedIndicators.json
        precalc_file = Path("precalculatedIndicators.json")
        if precalc_file.exists():
            with open(precalc_file, 'r') as f:
                data = json.load(f)
                current_indicators = data.get('indicators', [])
                print(f"\nCurrent indicators count: {len(current_indicators)}")
                
                # Check if this specific indicator exists
                exists = any(
                    ind.get('timeframe') == 'daily' and
                    ind.get('name') == 'supertrend' and
                    ind.get('params', {}).get('period') == 7 and
                    ind.get('params', {}).get('multiplier') == 3
                    for ind in current_indicators
                )
                print(f"Indicator already exists: {exists}")

if __name__ == "__main__":
    asyncio.run(test_new_indicator_detection())