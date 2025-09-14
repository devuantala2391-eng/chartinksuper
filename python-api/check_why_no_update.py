import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("INVESTIGATING WHY SUPERTREND DOESN'T UPDATE")
print("=" * 80)

# Check if there are multiple versions of the procedure
print("\n1. ALL DAILY SUPERTREND PROCEDURES:")
print("-" * 80)

cur.execute("""
    SELECT
        proname,
        oid,
        pg_get_function_arguments(oid) as args
    FROM pg_proc
    WHERE proname LIKE '%daily_supertrend%'
    ORDER BY proname, oid
""")

for name, oid, args in cur.fetchall():
    print(f"{name} (OID: {oid})")
    print(f"  Args: {args}")

# Check if we have duplicate procedures
print("\n2. CHECKING FOR DUPLICATE PROCEDURES:")
print("-" * 80)

cur.execute("""
    SELECT proname, COUNT(*) as count
    FROM pg_proc
    WHERE proname = 'calculate_daily_supertrend_for_symbol'
    GROUP BY proname
""")

for name, count in cur.fetchall():
    print(f"{name}: {count} version(s)")
    if count > 1:
        print("WARNING: Multiple versions exist! This could cause the wrong one to be called!")

# Let's check what happens when we call with explicit symbol
print("\n3. TESTING WITH EXPLICIT SYMBOL:")
print("-" * 80)

# First ensure ATR exists
cur.execute("SELECT * FROM calculate_atr(10, '20MICRONS')")
atr_result = cur.fetchone()
print(f"ATR result: {atr_result}")
conn.commit()

# Now try with explicit symbol
cur.execute("""
    SELECT * FROM calculate_daily_supertrend_for_symbol('20MICRONS', 10, 3, TRUE)
""")
result = cur.fetchone()
print(f"With symbol '20MICRONS': {result}")
conn.commit()

# Check the values
cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_supertrend_10_3')::numeric as st
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number = 999
""")

row = cur.fetchone()
if row:
    seq, st = row
    print(f"Result: Seq {seq} has SuperTrend={st}")
    if abs(float(st) - 250.01) < 0.1:
        print("SUCCESS when called with explicit symbol!")

cur.close()
conn.close()