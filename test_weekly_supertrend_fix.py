"""
Test script to verify weekly SuperTrend is stored with correct prefix
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_weekly_supertrend():
    """Test that weekly_supertrend_10_3 is correctly calculated and stored with prefix"""
    
    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("\n=== Testing Weekly SuperTrend Fix ===\n")
        
        # Step 1: Clear any old format indicators first
        print("Step 1: Removing old format indicators...")
        result = await conn.fetchrow("""
            SELECT * FROM remove_old_format_indicators('20MICRONS')
        """)
        print(f"Removal result: {dict(result)}")
        
        # Step 2: Calculate weekly SuperTrend with prefix using new procedure
        print("\nStep 2: Calculating weekly SuperTrend with prefix...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_weekly_monthly_supertrend('weekly', 10, 3.0, '20MICRONS')
        """)
        print(f"Calculation result: {dict(result)}")
        
        # Step 3: Check the actual database values
        print("\nStep 3: Checking database values...")
        rows = await conn.fetch("""
            SELECT 
                candle_key_id,
                indicators
            FROM daily_candles 
            WHERE symbol = '20MICRONS'
            AND indicators IS NOT NULL
            ORDER BY candle_sequence_number DESC
            LIMIT 5
        """)
        
        print("\nLatest 5 rows with indicators:")
        for row in rows:
            indicators = json.loads(row['indicators']) if isinstance(row['indicators'], str) else row['indicators']
            print(f"\nCandle {row['candle_key_id']}:")
            
            # Check for both old and new format
            has_old = False
            has_new = False
            
            if 'supertrend_10_3' in indicators:
                has_old = True
                print(f"  [X] OLD FORMAT: supertrend_10_3 = {indicators['supertrend_10_3']}")
            
            if 'weekly_supertrend_10_3' in indicators:
                has_new = True
                print(f"  [OK] NEW FORMAT: weekly_supertrend_10_3 = {indicators['weekly_supertrend_10_3']}")
            
            if 'supertrend_10_3_direction' in indicators:
                print(f"  [X] OLD FORMAT: supertrend_10_3_direction = {indicators['supertrend_10_3_direction']}")
            
            if 'weekly_supertrend_10_3_direction' in indicators:
                print(f"  [OK] NEW FORMAT: weekly_supertrend_10_3_direction = {indicators['weekly_supertrend_10_3_direction']}")
        
        # Step 4: Test auto-calculation trigger
        print("\n\nStep 4: Testing auto-calculation with dynamic_indicator_manager...")
        
        # Import and test the manager
        import sys
        sys.path.append('D:\\chartinksuper\\python-api')
        from services.dynamic_indicator_manager import dynamic_indicator_manager
        
        await dynamic_indicator_manager.initialize()
        
        # Simulate auto-calculation for weekly SuperTrend
        success = await dynamic_indicator_manager.calculate_and_store_indicator(
            indicator_def={
                'name': 'SuperTrend',
                'timeframe': 'weekly',
                'params': {'period': 10, 'multiplier': 3.0}
            }
        )
        
        print(f"Auto-calculation success: {success}")
        
        # Check database again
        print("\nStep 5: Re-checking database after auto-calculation...")
        rows = await conn.fetch("""
            SELECT 
                candle_key_id,
                indicators
            FROM daily_candles 
            WHERE symbol = '20MICRONS'
            AND indicators IS NOT NULL
            ORDER BY candle_sequence_number DESC
            LIMIT 3
        """)
        
        for row in rows:
            indicators = json.loads(row['indicators']) if isinstance(row['indicators'], str) else row['indicators']
            print(f"\nCandle {row['candle_key_id']}:")
            
            if 'supertrend_10_3' in indicators:
                print(f"  [X] OLD FORMAT STILL EXISTS: supertrend_10_3 = {indicators['supertrend_10_3']}")
            
            if 'weekly_supertrend_10_3' in indicators:
                print(f"  [OK] NEW FORMAT EXISTS: weekly_supertrend_10_3 = {indicators['weekly_supertrend_10_3']}")
        
        await dynamic_indicator_manager.close()
        
        print("\n=== Test Complete ===\n")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(test_weekly_supertrend())