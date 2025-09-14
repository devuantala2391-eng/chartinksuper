import psycopg2
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dynamic_indicator_manager import dynamic_indicator_manager

async def test_hard_refresh():
    print("TESTING HARD REFRESH FIX")
    print("=" * 80)

    # First check current database values
    conn = psycopg2.connect(
        host="localhost",
        database="nse_highspeed",
        user="postgres",
        password="123"
    )
    cur = conn.cursor()

    print("\n1. BEFORE FIX - Current database values:")
    print("-" * 80)

    cur.execute("""
        SELECT
            candle_sequence_number,
            (indicators->>'daily_supertrend_10_3')::numeric as st,
            (indicators->>'daily_supertrend_10_3_direction')::integer as dir
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND candle_sequence_number = 999
    """)

    row = cur.fetchone()
    if row:
        seq, st, dir = row
        print(f"Seq {seq}: SuperTrend={st:.2f}, Direction={dir}")
        if abs(float(st) - 208.63) < 0.1:
            print("PROBLEM: Still has OLD WRONG value (208.63)")
        elif abs(float(st) - 250.01) < 0.1:
            print("GOOD: Has CORRECT value (250.01)")

    # Now simulate what hard-refresh does - call dynamic_indicator_manager
    print("\n2. SIMULATING HARD REFRESH - Calling dynamic_indicator_manager:")
    print("-" * 80)

    await dynamic_indicator_manager.initialize()

    # This is what gets called during hard refresh for SuperTrend
    success = await dynamic_indicator_manager.calculate_and_store_indicator(
        indicator_def={
            'name': 'supertrend',
            'params': {'period': 10, 'multiplier': 3},
            'timeframe': 'daily'
        }
    )

    print(f"Dynamic indicator manager result: {success}")

    # Check values after the call
    print("\n3. AFTER FIX - Database values:")
    print("-" * 80)

    cur.execute("""
        SELECT
            candle_sequence_number,
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

    for row in cur.fetchall():
        seq, st, dir = row
        exp_st = expected[seq]

        if abs(float(st) - exp_st) < 0.1:
            status = "CORRECT"
        else:
            status = f"WRONG (expected {exp_st:.2f})"

        print(f"Seq {seq}: SuperTrend={st:.2f}, Direction={dir} - {status}")

    print("\n" + "=" * 80)
    print("VERIFICATION:")
    print("-" * 80)

    # Final verification
    cur.execute("""
        SELECT (indicators->>'daily_supertrend_10_3')::numeric as st
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND candle_sequence_number = 999
    """)

    st = cur.fetchone()[0]
    if abs(float(st) - 250.01) < 0.1:
        print("SUCCESS: The fix is working!")
        print("Hard refresh now uses the CORRECT stored procedure")
        print("Values will be correct after server restart and hard refresh")
    else:
        print(f"PROBLEM: Still getting wrong value ({st:.2f} instead of 250.01)")
        print("Further investigation needed")

    cur.close()
    conn.close()

if __name__ == "__main__":
    asyncio.run(test_hard_refresh())