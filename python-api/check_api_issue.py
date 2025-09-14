import psycopg2
import requests

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("INVESTIGATING API vs DATABASE MISMATCH")
print("="*80)

# 1. Check what's in the database RIGHT NOW
print("\n1. CURRENT DATABASE VALUES (sequence 999):")
print("-"*80)

cur.execute("""
    SELECT
        candle_sequence_number,
        close,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number = 999
""")

row = cur.fetchone()
if row:
    seq, close, st, dir = row
    print(f"Seq {seq}: Close={close:.2f}, SuperTrend={st}, Direction={dir}")
    if st and abs(float(st) - 208.63) < 0.1:
        print("WARNING: Still has OLD value (208.63)!")
    elif st and abs(float(st) - 250.01) < 0.1:
        print("Has CORRECT value (250.01)")

# 2. Check which stored procedures exist
print("\n2. AVAILABLE STORED PROCEDURES:")
print("-"*80)

cur.execute("""
    SELECT proname, oid
    FROM pg_proc
    WHERE proname LIKE '%daily_supertrend%'
    ORDER BY proname
""")

for name, oid in cur.fetchall():
    print(f"  - {name} (OID: {oid})")

# 3. Check if our fixed procedure exists
print("\n3. CHECKING FOR OUR FIXED PROCEDURE:")
print("-"*80)

cur.execute("""
    SELECT proname
    FROM pg_proc
    WHERE proname = 'calculate_supertrend_for_symbol'
""")

if cur.fetchone():
    print("  ✓ calculate_supertrend_for_symbol EXISTS")
else:
    print("  ✗ calculate_supertrend_for_symbol MISSING")

# 4. Check what happens when we refresh
print("\n4. WHAT HAPPENS DURING REFRESH:")
print("-"*80)

# Check if migrations are applied
cur.execute("""
    SELECT COUNT(*)
    FROM pg_proc
    WHERE proname = 'calculate_atr'
""")

if cur.fetchone()[0] > 0:
    print("  ✓ ATR procedure exists")
else:
    print("  ✗ ATR procedure missing")

# 5. Force recalculation with correct procedure
print("\n5. FORCING RECALCULATION:")
print("-"*80)

# First ensure ATR is calculated
print("Calculating ATR...")
cur.execute("SELECT * FROM calculate_atr(10, '20MICRONS')")
result = cur.fetchone()
print(f"  ATR result: {result}")
conn.commit()

# Then calculate SuperTrend
print("Calculating Daily SuperTrend...")
cur.execute("SELECT * FROM calculate_daily_supertrend_for_symbol('20MICRONS', 10, 3, TRUE)")
result = cur.fetchone()
print(f"  SuperTrend result: {result}")
conn.commit()

# Check the value again
print("\n6. VALUE AFTER RECALCULATION:")
print("-"*80)

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
    print(f"Seq {seq}: SuperTrend={st}, Direction={dir}")
    print(f"Expected: SuperTrend=250.01, Direction=0")
    if st and abs(float(st) - 250.01) < 0.1:
        print("SUCCESS: Value is now correct!")
    else:
        print("PROBLEM: Value is still wrong!")

cur.close()
conn.close()