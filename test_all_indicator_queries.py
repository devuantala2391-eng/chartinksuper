"""
Comprehensive test for all indicator queries with proper timeframe prefixes
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_indicator_normalization():
    """Test that all indicator queries are normalized correctly"""
    
    # Import the services
    import sys
    sys.path.append('D:\\chartinksuper\\python-api')
    from services.query_service import resolve_field_name
    from services.highspeed_query_validator import HighSpeedQueryValidator
    
    validator = HighSpeedQueryValidator()
    
    test_cases = [
        # Daily indicators
        ("daily_supertrend_10_3", "daily_supertrend_10_3"),
        ("daily supertrend (10,3)", "daily_supertrend_10_3"),
        ("daily_supertrend_10_2", "daily_supertrend_10_2"),
        ("daily_pctchg", "daily_pctchg"),
        ("daily_pctchg_1", "daily_pctchg"),  # Legacy format
        
        # Weekly indicators
        ("weekly_supertrend_10_3", "weekly_supertrend_10_3"),
        ("weekly supertrend (10,3)", "weekly_supertrend_10_3"),
        ("weekly_supertrend_10_2", "weekly_supertrend_10_2"),
        ("weekly_pctchg", "weekly_pctchg"),
        
        # Monthly indicators
        ("monthly_supertrend_10_3", "monthly_supertrend_10_3"),
        ("monthly supertrend (10,3)", "monthly_supertrend_10_3"),
        ("monthly_pctchg", "monthly_pctchg"),
        
        # Decimal multipliers
        ("daily_supertrend_10_2.5", "daily_supertrend_10_2dot5"),
        ("weekly_supertrend_10_1.5", "weekly_supertrend_10_1dot5"),
        
        # Legacy unprefixed (should default to daily)
        ("supertrend_10_3", "daily_supertrend_10_3"),
    ]
    
    print("="*60)
    print("TESTING FIELD NAME RESOLUTION")
    print("="*60)
    
    for input_field, expected in test_cases:
        resolved = resolve_field_name(input_field)
        normalized = validator._normalize_field_name(resolved)
        
        status = "[OK]" if normalized == expected else "[FAIL]"
        print(f"\n{status} Input: {input_field}")
        print(f"  Resolved: {resolved}")
        print(f"  Normalized: {normalized}")
        print(f"  Expected: {expected}")
        
        if normalized != expected:
            print(f"  ERROR: Mismatch!")

async def test_indicator_parsing():
    """Test that indicators are parsed with correct timeframes"""
    
    import sys
    sys.path.append('D:\\chartinksuper\\python-api')
    from services.highspeed_query_validator import HighSpeedQueryValidator
    
    validator = HighSpeedQueryValidator()
    
    test_cases = [
        ("daily_supertrend_10_3", {"name": "SuperTrend", "timeframe": "daily", "params": {"period": 10.0, "multiplier": 3.0}}),
        ("weekly_supertrend_10_3", {"name": "SuperTrend", "timeframe": "weekly", "params": {"period": 10.0, "multiplier": 3.0}}),
        ("monthly_supertrend_10_3", {"name": "SuperTrend", "timeframe": "monthly", "params": {"period": 10.0, "multiplier": 3.0}}),
        ("daily_supertrend_10_2", {"name": "SuperTrend", "timeframe": "daily", "params": {"period": 10.0, "multiplier": 2.0}}),
        ("weekly_supertrend_10_2", {"name": "SuperTrend", "timeframe": "weekly", "params": {"period": 10.0, "multiplier": 2.0}}),
        ("daily_pctchg", {"name": "PercentageChange", "timeframe": "daily", "params": {}}),
        ("weekly_pctchg", {"name": "PercentageChange", "timeframe": "weekly", "params": {}}),
        ("monthly_pctchg", {"name": "PercentageChange", "timeframe": "monthly", "params": {}}),
    ]
    
    print("\n" + "="*60)
    print("TESTING INDICATOR PARSING")
    print("="*60)
    
    for field_name, expected in test_cases:
        parsed = validator._parse_indicator_from_field(field_name)
        
        matches = True
        if parsed:
            matches = (
                parsed.get("name") == expected["name"] and
                parsed.get("timeframe") == expected["timeframe"] and
                parsed.get("params") == expected["params"]
            )
        else:
            matches = False
        
        status = "[OK]" if matches else "[FAIL]"
        print(f"\n{status} Field: {field_name}")
        print(f"  Parsed: {parsed}")
        print(f"  Expected: {expected}")
        
        if not matches:
            print(f"  ERROR: Mismatch!")

async def test_database_queries():
    """Test actual database queries with different indicators"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("\n" + "="*60)
        print("TESTING DATABASE QUERIES")
        print("="*60)
        
        # Test queries for each timeframe
        test_queries = [
            ("daily_supertrend_10_3", "indicators->'daily_supertrend_10_3'"),
            ("weekly_supertrend_10_3", "indicators->'weekly_supertrend_10_3'"),
            ("monthly_supertrend_10_3", "indicators->'monthly_supertrend_10_3'"),
            ("daily_pctchg", "indicators->'daily_pctchg'"),
            ("weekly_pctchg", "indicators->'weekly_pctchg'"),
            ("monthly_pctchg", "indicators->'monthly_pctchg'"),
        ]
        
        for indicator_name, json_path in test_queries:
            # Query to check if indicator exists
            query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT({json_path}) as with_indicator
                FROM daily_candles
                WHERE symbol = '20MICRONS'
            """
            
            result = await conn.fetchrow(query)
            
            if result['with_indicator'] > 0:
                # Get a sample value
                sample_query = f"""
                    SELECT 
                        candle_key_id,
                        {json_path} as indicator_value
                    FROM daily_candles
                    WHERE symbol = '20MICRONS'
                    AND {json_path} IS NOT NULL
                    ORDER BY candle_sequence_number DESC
                    LIMIT 1
                """
                sample = await conn.fetchrow(sample_query)
                
                print(f"\n[OK] {indicator_name}")
                print(f"  Found in {result['with_indicator']}/{result['total']} rows")
                if sample:
                    print(f"  Sample: {sample['candle_key_id']} = {sample['indicator_value']}")
            else:
                print(f"\n[MISSING] {indicator_name}")
                print(f"  Not found in any of {result['total']} rows")
        
    finally:
        await conn.close()

async def main():
    """Run all tests"""
    await test_indicator_normalization()
    await test_indicator_parsing()
    await test_database_queries()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60)

if __name__ == '__main__':
    asyncio.run(main())