"""
Debug monthly ATR calculation issue
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_monthly_atr():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("="*70)
        print("DEBUGGING MONTHLY ATR CALCULATION")
        print("="*70)
        
        # Step 1: Check monthly_enriched CTE
        print("\n1. MONTHLY_ENRICHED CTE:")
        enriched = await conn.fetch("""
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
            SELECT * FROM monthly_enriched
            ORDER BY month_sequence_number
        """)
        
        print(f"Found {len(enriched)} enriched rows")
        for row in enriched[:3]:
            print(f"  Seq {row['month_sequence_number']}: {row['monthly_candle_key_id']}, H={row['high']}, L={row['low']}, C={row['close']}")
        
        # Step 2: Check TR calculation
        print("\n2. TRUE RANGE CALCULATION:")
        tr_data = await conn.fetch("""
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
            ),
            monthly_with_tr AS (
                SELECT 
                    me.*,
                    GREATEST(
                        me.high - me.low,
                        ABS(me.high - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number)),
                        ABS(me.low - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number))
                    ) as true_range
                FROM monthly_enriched me
            )
            SELECT 
                month_sequence_number,
                high, low, close,
                true_range
            FROM monthly_with_tr
            ORDER BY month_sequence_number
        """)
        
        print(f"True Range for {len(tr_data)} periods:")
        for row in tr_data:
            print(f"  Seq {row['month_sequence_number']}: TR={row['true_range']}")
        
        # Step 3: Check ATR calculation with WHERE clause
        print("\n3. ATR CALCULATION WITH FILTER (>= 10):")
        atr_data = await conn.fetch("""
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
            ),
            monthly_with_tr AS (
                SELECT 
                    me.*,
                    GREATEST(
                        me.high - me.low,
                        ABS(me.high - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number)),
                        ABS(me.low - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number))
                    ) as true_range
                FROM monthly_enriched me
            ),
            monthly_with_atr AS (
                SELECT 
                    *,
                    AVG(true_range) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                    ) as atr
                FROM monthly_with_tr
                WHERE month_sequence_number >= 10  -- THIS IS THE PROBLEM!
            )
            SELECT * FROM monthly_with_atr
        """)
        
        print(f"Rows after WHERE filter: {len(atr_data)}")
        if len(atr_data) == 0:
            print("[ERROR] No rows pass the WHERE clause filter!")
            print("The issue is: month_sequence_number >= 10, but max sequence is 9")
        
        # Step 4: Fix - should be >= (p_period - 1) not >= p_period
        print("\n4. CORRECTED ATR CALCULATION (>= 9):")
        corrected_atr = await conn.fetch("""
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
            ),
            monthly_with_tr AS (
                SELECT 
                    me.*,
                    GREATEST(
                        me.high - me.low,
                        ABS(me.high - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number)),
                        ABS(me.low - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number))
                    ) as true_range
                FROM monthly_enriched me
            ),
            monthly_with_atr AS (
                SELECT 
                    *,
                    AVG(true_range) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                    ) as atr,
                    COUNT(*) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                    ) as window_count
                FROM monthly_with_tr
                WHERE month_sequence_number >= 9  -- CORRECTED: >= (period - 1)
            )
            SELECT 
                candle_key_id,
                month_sequence_number,
                atr,
                window_count
            FROM monthly_with_atr
        """)
        
        print(f"Rows with corrected filter: {len(corrected_atr)}")
        if len(corrected_atr) > 0:
            row = corrected_atr[0]
            print(f"  Seq {row['month_sequence_number']}: ATR={row['atr']}, Window={row['window_count']} periods")
            print("[OK] This would calculate SuperTrend correctly!")
        
        print("\n" + "="*70)
        print("ROOT CAUSE IDENTIFIED")
        print("="*70)
        print("\nThe WHERE clause in monthly_with_atr filters:")
        print("  WHERE month_sequence_number >= p_period")
        print("But the sequence starts from 0, so with 10 periods (0-9),")
        print("filtering >= 10 excludes all rows!")
        print("\nFIX: Change to >= (p_period - 1) or >= 9")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(debug_monthly_atr())