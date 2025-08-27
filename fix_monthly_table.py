#!/usr/bin/env python3
"""
Fix monthly_candles table structure
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def fix_monthly_table():
    """Fix monthly table structure"""
    try:
        print("Initializing database connection...")
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            print("Dropping existing monthly_candles table...")
            await conn.execute("DROP TABLE IF EXISTS monthly_candles")
            
            print("Creating new monthly_candles table with correct structure...")
            await conn.execute("""
                CREATE TABLE monthly_candles (
                    symbol VARCHAR(20) NOT NULL,
                    month_start_timestamp BIGINT NOT NULL,
                    month_start_date DATE NOT NULL,
                    open DECIMAL(20,6) NOT NULL,
                    high DECIMAL(20,6) NOT NULL,
                    low DECIMAL(20,6) NOT NULL,
                    close DECIMAL(20,6) NOT NULL,
                    volume BIGINT NOT NULL,
                    trading_days INTEGER DEFAULT 20,
                    rsi_14 DECIMAL(10,4),
                    rsi_21 DECIMAL(10,4),
                    sma_10 DECIMAL(10,4),
                    sma_20 DECIMAL(10,4),
                    ema_12 DECIMAL(10,4),
                    ema_26 DECIMAL(10,4),
                    supertrend_10_2 DECIMAL(10,4),
                    supertrend_signal_10_2 INTEGER,
                    supertrend_10_3 DECIMAL(10,4),
                    supertrend_signal_10_3 INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, month_start_timestamp)
                )
            """)
            
            print("Creating indexes for monthly_candles...")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_monthly_symbol_timestamp ON monthly_candles(symbol, month_start_timestamp DESC)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_monthly_timestamp ON monthly_candles(month_start_timestamp DESC)")
            
            print("Monthly_candles table fixed successfully!")
        
    except Exception as e:
        print(f"Failed to fix table: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(fix_monthly_table())