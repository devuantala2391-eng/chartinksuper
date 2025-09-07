#!/usr/bin/env python3
"""
Find available symbols and dates with EMA data
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def find_available_data():
    """Find symbols and dates that have EMA data"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("=== Finding Available Data ===")
        
        # Find symbols that have weekly EMA data
        print("\n1. Symbols with weekly_ema_9 data:")
        symbols_with_ema = await conn.fetch("""
            SELECT 
                symbol,
                COUNT(*) as days_with_ema,
                MIN(datetime) as earliest_date,
                MAX(datetime) as latest_date
            FROM daily_candles
            WHERE indicators ? 'weekly_ema_9'
                AND (indicators->>'weekly_ema_9')::numeric IS NOT NULL
            GROUP BY symbol
            ORDER BY days_with_ema DESC
            LIMIT 10
        """)
        
        for row in symbols_with_ema:
            print(f"  {row['symbol']}: {row['days_with_ema']} days, {row['earliest_date']} to {row['latest_date']}")
        
        if symbols_with_ema:
            # Pick the first symbol with most data
            test_symbol = symbols_with_ema[0]['symbol']
            latest_date = symbols_with_ema[0]['latest_date']
            
            print(f"\n2. Using {test_symbol} for debugging, latest date: {latest_date}")
            
            # Get some recent EMA values for this symbol
            recent_ema = await conn.fetch("""
                SELECT 
                    datetime,
                    weekly_close,
                    (indicators->>'weekly_ema_9')::numeric as weekly_ema_9
                FROM daily_candles
                WHERE symbol = $1
                    AND indicators ? 'weekly_ema_9'
                    AND (indicators->>'weekly_ema_9')::numeric IS NOT NULL
                ORDER BY datetime DESC
                LIMIT 5
            """, test_symbol)
            
            print(f"\n3. Recent EMA values for {test_symbol}:")
            for row in recent_ema:
                print(f"  {row['datetime']}: Weekly Close={row['weekly_close']}, EMA(9)={row['weekly_ema_9']}")
            
            # Check if we have weekly candle data for this symbol
            weekly_candles_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM weekly_candles
                WHERE symbol = $1
            """, test_symbol)
            
            print(f"\n4. Weekly candles for {test_symbol}: {weekly_candles_count}")
            
            if weekly_candles_count > 0:
                recent_weekly = await conn.fetch("""
                    SELECT 
                        week_start_datetime,
                        week_end_datetime,
                        close
                    FROM weekly_candles
                    WHERE symbol = $1
                    ORDER BY week_start_datetime DESC
                    LIMIT 5
                """, test_symbol)
                
                print(f"5. Recent weekly candles for {test_symbol}:")
                for row in recent_weekly:
                    print(f"  {row['week_start_datetime']} to {row['week_end_datetime']}: Close={row['close']}")
        
    except Exception as e:
        print(f"Error finding data: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_available_data())