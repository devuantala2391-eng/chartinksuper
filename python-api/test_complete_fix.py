import psycopg2
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dynamic_indicator_manager import dynamic_indicator_manager

async def test_complete_fix():
    print("TESTING COMPLETE FIX - ATR + SUPERTREND")
    print("=" * 80)

    conn = psycopg2.connect(
        host="localhost",
        database="nse_highspeed",
        user="postgres",
        password="123"
    )
    cur = conn.cursor()

    # 1. Clear existing indicators to simulate fresh state
    print("\n1. CLEARING EXISTING INDICATORS (simulating hard refresh):")
    print("-" * 80)

    cur.execute("""
        UPDATE daily_candles
        SET indicators = indicators - 'daily_atr_10' - 'daily_supertrend_10_3' - 'daily_supertrend_10_3_direction'
        WHERE symbol = '20MICRONS'
    """)
    conn.commit()
    print("Cleared ATR and SuperTrend indicators")

    # 2. Verify they're gone
    print("\n2. VERIFY INDICATORS ARE CLEARED:")
    print("-" * 80)

    cur.execute("""
        SELECT
            candle_sequence_number,
            (indicators->>'daily_atr_10')::numeric as atr,
            (indicators->>'daily_supertrend_10_3')::numeric as st
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND candle_sequence_number = 999
    """)

    row = cur.fetchone()
    if row:
        seq, atr, st = row
        print(f"Seq {seq}: ATR={'MISSING' if atr is None else atr}, SuperTrend={'MISSING' if st is None else st}")

    # 3. Now call dynamic_indicator_manager (simulating hard refresh)
    print("\n3. CALLING DYNAMIC_INDICATOR_MANAGER (like hard-refresh does):")
    print("-" * 80)

    await dynamic_indicator_manager.initialize()

    success = await dynamic_indicator_manager.calculate_and_store_indicator(
        indicator_def={
            'name': 'supertrend',
            'params': {'period': 10, 'multiplier': 3},
            'timeframe': 'daily'
        }
    )

    print(f"Result: {success}")

    # 4. Check final values
    print("\n4. FINAL VALUES AFTER FIX:")
    print("-" * 80)

    cur.execute("""
        SELECT
            candle_sequence_number,
            (indicators->>'daily_atr_10')::numeric as atr,
            (indicators->>'daily_supertrend_10_3')::numeric as st,
            (indicators->>'daily_supertrend_10_3_direction')::integer as dir
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND candle_sequence_number BETWEEN 997 AND 999
        ORDER BY candle_sequence_number DESC
    """)

    expected = {
        999: 250.01,
        998: 251.07,
        997: 251.77
    }

    all_correct = True
    for row in cur.fetchall():
        seq, atr, st, dir = row
        exp_st = expected[seq]

        if abs(float(st) - exp_st) < 0.1 and dir == 0:
            status = "CORRECT"
        else:
            status = f"WRONG (expected {exp_st:.2f}, dir=0)"
            all_correct = False

        print(f"Seq {seq}: ATR={atr:.2f}, SuperTrend={st:.2f}, Direction={dir} - {status}")

    print("\n" + "=" * 80)
    if all_correct:
        print("SUCCESS: The complete fix is working!")
        print("- ATR is calculated first as prerequisite")
        print("- SuperTrend uses the correct stored procedure")
        print("- Values match expected (250.01, 251.07, 251.77)")
        print("\nHard refresh will now produce correct values!")
    else:
        print("PROBLEM: Values still don't match")
        print("Further investigation needed")

    cur.close()
    conn.close()

if __name__ == "__main__":
    asyncio.run(test_complete_fix())