#!/usr/bin/env python3
"""
Drop conflicting PostgreSQL function
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def drop_function():
    """Drop conflicting function"""
    try:
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            print("Dropping conflicting function...")
            await conn.execute("DROP FUNCTION IF EXISTS calculate_weekly_percentage_change(text, integer)")
            print("Function dropped successfully!")
        
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(drop_function())