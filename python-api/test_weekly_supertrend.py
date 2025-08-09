import sys
sys.path.append('.')

from services.query_service import parse_query, validate_query_fields, resolve_field_name, detect_missing_indicators_from_fields
import json

def test_weekly_supertrend():
    """Test detection of weekly_supertrend_30_1.56"""
    
    test_query = "daily_pctchg_1 < 9 and daily_pctchg_1 > 0 and weekly_supertrend_30_1.56 > 20"
    
    print(f"Testing query: {test_query}")
    print("-" * 60)
    
    # Parse the query
    parsed = parse_query(test_query)
    print("Parsed query conditions:")
    for i, cond in enumerate(parsed.get("conditions", [])):
        print(f"  Condition {i+1}: {cond}")
    print()
    
    # Validate fields
    validation = validate_query_fields(parsed)
    print(f"Validation result: {validation['valid']}")
    if not validation['valid']:
        print(f"Missing fields: {validation.get('missing_fields', [])}")
        print()
        
        # Test field resolution
        for field in validation.get('missing_fields', []):
            resolved = resolve_field_name(field)
            print(f"Field: {field}")
            print(f"Resolved: {resolved}")
            
            # Check if it can be converted to indicator
            indicators = detect_missing_indicators_from_fields([field])
            if indicators:
                print(f"Indicator config: {json.dumps(indicators[0], indent=2)}")
            else:
                print("No indicator config generated")
            print("-" * 40)

if __name__ == "__main__":
    test_weekly_supertrend()