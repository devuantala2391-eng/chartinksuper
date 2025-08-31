"""
Test that decimal multipliers are properly formatted in indicator keys
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_decimal_multipliers():
    """Test various decimal multipliers to ensure proper formatting"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("="*70)
        print("TESTING DECIMAL MULTIPLIER FORMATTING")
        print("="*70)
        
        # Test cases: (period, multiplier, expected_key)
        test_cases = [
            (10, 1.6, 'daily_supertrend_10_1dot6'),
            (10, 2.5, 'daily_supertrend_10_2dot5'),
            (10, 3.0, 'daily_supertrend_10_3'),
            (10, 1.25, 'daily_supertrend_10_1dot25'),
            (14, 2.0, 'daily_supertrend_14_2'),
            (7, 1.5, 'daily_supertrend_7_1dot5'),
            # Test the problematic case
            (10, 1.600000000000000088817841970012523233890533447265625, 'daily_supertrend_10_1dot6'),
        ]
        
        for period, multiplier, expected_key in test_cases:
            print(f"\nTest: SuperTrend({period}, {multiplier})")
            print(f"Expected key: {expected_key}")
            
            # Calculate using stored procedure
            result = await conn.fetchrow("""
                SELECT * FROM calculate_timeframe_supertrend('daily', $1, $2, '20MICRONS')
            """, period, multiplier)
            
            if result:
                actual_key = result.get('indicator_key', 'N/A')
                print(f"Actual key: {actual_key}")
                
                if actual_key == expected_key:
                    print("[OK] Key formatted correctly")
                else:
                    print(f"[ERROR] Key mismatch!")
                    print(f"  Expected: {expected_key}")
                    print(f"  Got: {actual_key}")
                
                # Check what's actually in the database
                check_result = await conn.fetchrow("""
                    SELECT 
                        candle_key_id,
                        indicators
                    FROM daily_candles
                    WHERE symbol = '20MICRONS'
                    AND indicators IS NOT NULL
                    ORDER BY candle_sequence_number DESC
                    LIMIT 1
                """)
                
                if check_result and check_result['indicators']:
                    indicators = json.loads(check_result['indicators']) if isinstance(check_result['indicators'], str) else check_result['indicators']
                    
                    # Check if the key exists
                    if actual_key in indicators:
                        print(f"  Value in DB: {indicators[actual_key]}")
                    
                    # Check for any long decimal keys
                    for key in indicators.keys():
                        if 'supertrend' in key and len(key) > 50:
                            print(f"  [WARNING] Found long key: {key[:50]}...")
        
        print("\n" + "="*70)
        print("TEST PYTHON UTILITY FUNCTIONS")
        print("="*70)
        
        import sys
        sys.path.append('D:\\chartinksuper\\python-api')
        from services.utils import format_multiplier_for_key, format_period_for_key
        
        python_test_cases = [
            (1.6, '1dot6'),
            (2.5, '2dot5'),
            (3.0, '3'),
            (1.25, '1dot25'),
            (2.0, '2'),
            (1.5, '1dot5'),
            (1.600000000000000088817841970012523233890533447265625, '1dot6'),
        ]
        
        for value, expected in python_test_cases:
            result = format_multiplier_for_key(value)
            status = "[OK]" if result == expected else "[ERROR]"
            print(f"{status} {value} -> {result} (expected: {expected})")
        
        print("\n" + "="*70)
        print("TESTS COMPLETE")
        print("="*70)
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(test_decimal_multipliers())