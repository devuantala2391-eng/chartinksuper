import sys
sys.path.append('.')

from services.query_service import resolve_field_name, detect_missing_indicators_from_fields

def test_field_resolution():
    """Test that field names are properly resolved and converted to indicators."""
    
    test_fields = [
        "daily_supertrend_8_2.5",
        "daily_rsi_25",
        "daily_bb_upper_15_1.5",
        "weekly_supertrend_12_3.5",
        "daily_sma_100"
    ]
    
    print("Testing field resolution:")
    print("-" * 60)
    
    for field in test_fields:
        resolved = resolve_field_name(field)
        print(f"Original: {field}")
        print(f"Resolved: {resolved}")
        
        # Test if it can be converted to an indicator
        indicators = detect_missing_indicators_from_fields([field])
        if indicators:
            print(f"Indicator config: {indicators[0]}")
        else:
            print("No indicator configuration generated")
        print("-" * 40)

if __name__ == "__main__":
    test_field_resolution()