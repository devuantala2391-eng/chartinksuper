#!/usr/bin/env python3
"""
Test script to verify percentage change stored procedures are working
"""

import asyncio
import logging
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db
from services.postgres_indicator_service import postgres_indicator_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_percentage_procedures():
    """Test the percentage change procedures"""
    try:
        print("Initializing database connection...")
        await ultra_fast_db.initialize()
        
        print("Initializing PostgreSQL indicator service...")
        success = await postgres_indicator_service.initialize()
        if not success:
            print("Failed to initialize PostgreSQL indicator service")
            return
            
        print("PostgreSQL indicator service initialized successfully")
        
        # Test if we have any data
        print("Checking available data...")
        async with ultra_fast_db.pool.acquire() as conn:
            # Check daily candles
            daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
            print(f"Daily candles: {daily_count} rows")
            
            # Check weekly candles 
            try:
                weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
                print(f"Weekly candles: {weekly_count} rows")
            except Exception as e:
                print(f"Weekly candles table issue: {e}")
            
            # Check some sample data
            if daily_count > 0:
                sample = await conn.fetchrow("SELECT symbol, timestamp, close FROM daily_candles ORDER BY timestamp DESC LIMIT 1")
                print(f"Latest candle: {sample['symbol']} - {sample['close']} at {sample['timestamp']}")
        
        # Test daily percentage change
        print("\nTesting daily percentage change calculation...")
        result = await postgres_indicator_service.calculate_percentage_change('daily')
        print(f"Daily result: {result}")
        
        # Test weekly percentage change
        print("\nTesting weekly percentage change calculation...")
        result = await postgres_indicator_service.calculate_percentage_change('weekly')
        print(f"Weekly result: {result}")
        
        # Test monthly percentage change
        print("\nTesting monthly percentage change calculation...")
        result = await postgres_indicator_service.calculate_percentage_change('monthly')
        print(f"Monthly result: {result}")
        
        # Check coverage
        print("\nChecking coverage...")
        for timeframe in ['daily', 'weekly', 'monthly']:
            coverage = await postgres_indicator_service.check_percentage_change_coverage(timeframe)
            print(f"{timeframe.title()} coverage: {coverage}")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool.is_closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(test_percentage_procedures())