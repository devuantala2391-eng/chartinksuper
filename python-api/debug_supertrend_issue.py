import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("DEBUGGING SUPERTREND ISSUE")
print("=" * 80)

# 1. Check if ATR exists
print("\n1. CHECKING ATR VALUES:")
print("-" * 80)

cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 995 AND 999
    ORDER BY candle_sequence_number DESC
""")

has_atr = True
for row in cur.fetchall():
    seq, atr = row
    if atr is None:
        has_atr = False
        print(f"Seq {seq}: ATR=MISSING")
    else:
        print(f"Seq {seq}: ATR={atr:.2f}")

if not has_atr:
    print("\nPROBLEM FOUND: ATR is missing!")
    print("SuperTrend cannot calculate correctly without ATR")
    print("Calculating ATR first...")

    # Calculate ATR
    cur.execute("SELECT * FROM calculate_atr(10, '20MICRONS')")
    result = cur.fetchone()
    print(f"ATR calculation result: {result}")
    conn.commit()

# 2. Now force recalculation with the CORRECT procedure
print("\n2. FORCING RECALCULATION WITH CORRECT PROCEDURE:")
print("-" * 80)

# First try the exact call that should work
cur.execute("""
    SELECT * FROM calculate_daily_supertrend_for_symbol('20MICRONS', 10, 3, TRUE)
""")
result = cur.fetchone()
print(f"Direct procedure call result: {result}")
conn.commit()

# 3. Check values after direct call
print("\n3. VALUES AFTER DIRECT PROCEDURE CALL:")
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
        status = f"WRONG (off by {abs(float(st) - exp_st):.2f})"

    print(f"Seq {seq}: SuperTrend={st:.2f}, Direction={dir} - {status}")

# 4. The real issue - check which procedure dynamic_indicator_manager is actually using
print("\n4. CHECKING PROCEDURE SIGNATURES:")
print("-" * 80)

# Check calculate_daily_supertrend_for_symbol signature
cur.execute("""
    SELECT
        proname,
        pg_get_function_arguments(oid) as arguments
    FROM pg_proc
    WHERE proname = 'calculate_daily_supertrend_for_symbol'
""")

for name, args in cur.fetchall():
    print(f"{name}: {args}")

print("\n" + "=" * 80)
print("DIAGNOSIS:")
print("-" * 80)
print("The issue is that updated_rows=0 means the procedure ran but didn't update.")
print("This happens when:")
print("1. ATR is missing (SuperTrend needs ATR)")
print("2. The procedure thinks values are already correct")
print("3. The procedure has a bug in the update logic")

cur.close()
conn.close()