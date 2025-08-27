#!/usr/bin/env python3
"""
Final test of monthly percentage change
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db
from services.postgres_indicator_service import postgres_indicator_service

async def test_final_monthly():
    """Final test of monthly percentage"""
    try:
        print("=== FINAL MONTHLY PERCENTAGE CHANGE TEST ===")
        
        await ultra_fast_db.initialize()
        
        # Initialize PostgreSQL indicator service
        success = await postgres_indicator_service.initialize()
        if not success:
            print("Failed to initialize PostgreSQL indicator service")
            return
            
        # Check monthly candles
        async with ultra_fast_db.pool.acquire() as conn:
            monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
            print(f"Monthly candles available: {monthly_count}")
            
            if monthly_count > 0:
                sample = await conn.fetchrow("SELECT symbol, month_start_timestamp, open, close FROM monthly_candles ORDER BY month_start_timestamp DESC LIMIT 1")
                print(f"Latest monthly candle: {dict(sample)}")
        
        # Test monthly percentage calculation
        print("\nCalculating monthly percentage change...")
        result = await postgres_indicator_service.calculate_percentage_change('monthly')
        print(f"Monthly percentage calculation result: {result}")
        
        # Check coverage
        coverage = await postgres_indicator_service.check_percentage_change_coverage('monthly')
        print(f"Monthly percentage coverage: {coverage}")
        
        # Show a sample of calculated monthly percentage
        if coverage.get('coverage_percentage', 0) > 0:
            async with ultra_fast_db.pool.acquire() as conn:
                sample_with_pct = await conn.fetchrow("""
                    SELECT symbol, timestamp, close, (indicators->>'monthly_pctchg')::numeric as monthly_pctchg 
                    FROM daily_candles 
                    WHERE indicators ? 'monthly_pctchg' 
                    AND (indicators->>'monthly_pctchg')::numeric IS NOT NULL
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
                if sample_with_pct:
                    print(f"Sample with monthly %: {dict(sample_with_pct)}")
                else:
                    print("No daily candles with monthly % found")
        
        print("\n=== TEST COMPLETED ===")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(test_final_monthly())