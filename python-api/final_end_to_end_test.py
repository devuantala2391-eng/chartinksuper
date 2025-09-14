import psycopg2
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dynamic_indicator_manager import dynamic_indicator_manager

async def final_test():
    print("FINAL END-TO-END TEST")
    print("=" * 80)
    print("This simulates exactly what happens during hard-refresh")
    print()

    conn = psycopg2.connect(
        host="localhost",
        database="nse_highspeed",
        user="postgres",
        password="123"
    )
    cur = conn.cursor()

    # 1. Clear indicators to simulate hard refresh
    print("1. CLEARING INDICATORS (simulating hard refresh):")
    print("-" * 80)

    cur.execute("""
        UPDATE daily_candles
        SET indicators = indicators - 'daily_atr_10' - 'daily_supertrend_10_3' - 'daily_supertrend_10_3_direction'
        WHERE symbol = '20MICRONS'
    """)
    conn.commit()
    print("Cleared indicators for 20MICRONS")

    # 2. Call dynamic_indicator_manager like hard-refresh does
    print("\n2. CALLING DYNAMIC_INDICATOR_MANAGER:")
    print("-" * 80)

    await dynamic_indicator_manager.initialize()

    # This is exactly what hard-refresh calls
    success = await dynamic_indicator_manager.calculate_and_store_indicator(
        indicator_def={
            'name': 'supertrend',
            'params': {'period': 10, 'multiplier': 3},
            'timeframe': 'daily'
        }
    )

    print(f"Dynamic indicator manager completed: {success}")

    # 3. Check the final values
    print("\n3. CHECKING FINAL VALUES:")
    print("-" * 80)

    cur.execute("""
        SELECT
            candle_sequence_number,
            close,
            (indicators->>'daily_atr_10')::numeric as atr,
            (indicators->>'daily_supertrend_10_3')::numeric as st,
            (indicators->>'daily_supertrend_10_3_direction')::integer as dir
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND candle_sequence_number BETWEEN 997 AND 999
        ORDER BY candle_sequence_number DESC
    """)

    expected = {
        999: (250.01, 0),
        998: (251.07, 0),
        997: (251.77, 0)
    }

    print("Seq  | Close   | ATR    | SuperTrend | Dir | Expected ST | Expected Dir | Status")
    print("-----|---------|--------|------------|-----|-------------|--------------|--------")

    all_correct = True
    for row in cur.fetchall():
        seq, close, atr, st, dir = row
        exp_st, exp_dir = expected[seq]

        if st and abs(float(st) - exp_st) < 0.1 and dir == exp_dir:
            status = "PERFECT"
        else:
            status = "WRONG"
            all_correct = False

        atr_str = f"{atr:.2f}" if atr else "NONE"
        st_str = f"{st:.2f}" if st else "NONE"

        print(f"{seq:4} | {close:7.2f} | {atr_str:6} | {st_str:10} | {dir:3} | {exp_st:11.2f} | {exp_dir:12} | {status}")

    print("\n" + "=" * 80)
    print("TEST RESULT:")
    print("-" * 80)

    if all_correct:
        print("SUCCESS: COMPLETE FIX IS WORKING!")
        print("")
        print("What was fixed:")
        print("1. Added calculate_supertrend.sql to migration service")
        print("2. Changed dynamic_indicator_manager to use correct procedures")
        print("3. Added ATR calculation before SuperTrend")
        print("4. Fixed procedure call to handle all symbols properly")
        print("")
        print("The server will now produce correct values after:")
        print("- Starting with run_server.bat")
        print("- Calling hard-refresh API")
        print("- Querying for SuperTrend values")
    else:
        print("PROBLEM: Values still incorrect")
        print("Check the output above for details")

    cur.close()
    conn.close()

if __name__ == "__main__":
    asyncio.run(final_test())