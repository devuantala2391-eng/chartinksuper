"""
Debug why monthly indicators are not being calculated
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_monthly():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("="*70)
        print("DEBUGGING MONTHLY INDICATOR CALCULATION")
        print("="*70)
        
        # 1. Check monthly_candles table
        print("\n1. MONTHLY_CANDLES TABLE STATUS:")
        print("-"*40)
        
        result = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT symbol) as symbols,
                MIN(month_start_timestamp) as earliest,
                MAX(month_start_timestamp) as latest
            FROM monthly_candles
            WHERE symbol = '20MICRONS'
        """)
        
        print(f"Total rows for 20MICRONS: {result['total_rows']}")
        print(f"Date range: {result['earliest']} to {result['latest']}")
        
        # Check month_sequence_number
        sequence_check = await conn.fetch("""
            SELECT 
                monthly_candle_key_id,
                month_sequence_number,
                open, high, low, close
            FROM monthly_candles
            WHERE symbol = '20MICRONS'
            ORDER BY month_sequence_number DESC
            LIMIT 5
        """)
        
        print("\nLatest monthly candles:")
        for row in sequence_check:
            print(f"  Key: {row['monthly_candle_key_id']}, Seq: {row['month_sequence_number']}, OHLC: {row['open']}/{row['high']}/{row['low']}/{row['close']}")
        
        # 2. Check daily_candles monthly columns
        print("\n2. DAILY_CANDLES MONTHLY COLUMNS:")
        print("-"*40)
        
        result = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_with_monthly,
                COUNT(monthly_candle_key_id) as with_key,
                COUNT(monthly_high) as with_high,
                COUNT(monthly_low) as with_low,
                COUNT(monthly_close) as with_close
            FROM daily_candles
            WHERE symbol = '20MICRONS'
        """)
        
        print(f"Rows with monthly_candle_key_id: {result['with_key']}")
        print(f"Rows with monthly OHLC data: H:{result['with_high']}, L:{result['with_low']}, C:{result['with_close']}")
        
        # Sample monthly data in daily_candles
        sample = await conn.fetch("""
            SELECT 
                candle_key_id,
                monthly_candle_key_id,
                monthly_high,
                monthly_low,
                monthly_close
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND monthly_high IS NOT NULL
            ORDER BY candle_sequence_number DESC
            LIMIT 5
        """)
        
        print("\nSample daily_candles with monthly data:")
        for row in sample:
            print(f"  {row['candle_key_id']}: monthly_key={row['monthly_candle_key_id']}, H={row['monthly_high']}, L={row['monthly_low']}, C={row['monthly_close']}")
        
        # 3. Try to manually calculate monthly SuperTrend
        print("\n3. MANUAL MONTHLY SUPERTREND CALCULATION TEST:")
        print("-"*40)
        
        # Check what the stored procedure sees
        test_result = await conn.fetchrow("""
            WITH monthly_enriched AS (
                SELECT DISTINCT ON (dc.monthly_candle_key_id)
                    dc.candle_key_id,
                    dc.symbol,
                    dc.monthly_candle_key_id,
                    mc.month_sequence_number,
                    dc.monthly_high as high,
                    dc.monthly_low as low,
                    dc.monthly_close as close,
                    dc.candle_sequence_number
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = '20MICRONS'
                AND dc.monthly_high IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.monthly_candle_key_id, dc.candle_sequence_number DESC
            )
            SELECT 
                COUNT(*) as enriched_rows,
                MIN(month_sequence_number) as min_seq,
                MAX(month_sequence_number) as max_seq
            FROM monthly_enriched
        """)
        
        print(f"Enriched monthly rows: {test_result['enriched_rows']}")
        print(f"Sequence range: {test_result['min_seq']} to {test_result['max_seq']}")
        
        # Check if we have enough data for ATR calculation (need at least 10 periods)
        if test_result['enriched_rows'] and test_result['enriched_rows'] >= 10:
            print(f"[OK] Have {test_result['enriched_rows']} monthly periods (need 10 for ATR)")
        else:
            print(f"[ERROR] Only have {test_result['enriched_rows']} monthly periods (need at least 10 for ATR)")
        
        # 4. Test the actual stored procedure
        print("\n4. TESTING STORED PROCEDURE:")
        print("-"*40)
        
        proc_result = await conn.fetchrow("""
            SELECT * FROM calculate_weekly_monthly_supertrend('monthly', 10, 3.0, '20MICRONS')
        """)
        
        print(f"Procedure result: {dict(proc_result)}")
        
        # 5. Check why no rows are updated
        print("\n5. CHECKING UPDATE LOGIC:")
        print("-"*40)
        
        # Check if the WHERE clause is filtering out all rows
        check_result = await conn.fetchrow("""
            SELECT COUNT(*) as would_update
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND monthly_candle_key_id IS NOT NULL
            AND (
                NOT (indicators ? 'monthly_supertrend_10_3') OR 
                (indicators->'monthly_supertrend_10_3') IS NULL
            )
        """)
        
        print(f"Rows that would be updated: {check_result['would_update']}")
        
        # Check existing monthly indicators
        existing = await conn.fetchrow("""
            SELECT COUNT(*) as has_monthly_indicator
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND indicators ? 'monthly_supertrend_10_3'
        """)
        
        print(f"Rows already having monthly_supertrend_10_3: {existing['has_monthly_indicator']}")
        
        print("\n" + "="*70)
        print("DIAGNOSIS COMPLETE")
        print("="*70)
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(debug_monthly())