import psycopg2
import json

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

symbol = '20MICRONS'

print("VERIFYING SUPERTREND VALUES FOR END-TO-END TEST")
print("="*80)

# Check sequence 999 specifically
cur.execute("""
    SELECT
        candle_sequence_number,
        close,
        (indicators->>'daily_supertrend_10_3')::numeric as daily_st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as daily_dir,
        (indicators->>'weekly_supertrend_10_3')::numeric as weekly_st,
        (indicators->>'weekly_supertrend_10_3_direction')::integer as weekly_dir,
        (indicators->>'monthly_supertrend_10_3')::numeric as monthly_st,
        (indicators->>'monthly_supertrend_10_3_direction')::integer as monthly_dir
    FROM daily_candles
    WHERE symbol = %s
    AND candle_sequence_number = 999
""", (symbol,))

row = cur.fetchone()
if row:
    seq, close, dst, ddir, wst, wdir, mst, mdir = row

    print(f"Sequence 999 Current Values:")
    print(f"  Close: {close}")
    print()
    print("Timeframe   | Actual Value | Actual Dir | Expected Value | Expected Dir | Match")
    print("------------|--------------|------------|----------------|--------------|-------")

    # Daily
    daily_match = "YES" if dst and abs(float(dst) - 250.01) < 0.1 and ddir == 0 else "NO"
    print(f"Daily       | {dst:12} | {ddir:10} | 250.01         | 0            | {daily_match}")

    # Weekly
    weekly_match = "YES" if wst and abs(float(wst) - 193.81) < 0.5 and wdir == 1 else "NO"
    print(f"Weekly      | {wst:12} | {wdir:10} | 193.81         | 1            | {weekly_match}")

    # Monthly
    monthly_match = "YES" if mst and abs(float(mst) - 337.11) < 0.5 and mdir == 0 else "NO"
    print(f"Monthly     | {mst:12} | {mdir:10} | 337.11         | 0            | {monthly_match}")
else:
    print("No data found for sequence 999")

# Test queries that should return matches
print("\n" + "="*80)
print("TESTING CURL QUERIES:")
print("="*80)

# Test daily query
cur.execute("""
    SELECT COUNT(*)
    FROM daily_candles
    WHERE symbol = %s
    AND (indicators->>'daily_supertrend_10_3')::numeric < 300
""", (symbol,))
daily_count = cur.fetchone()[0]
print(f"\n1. Daily SuperTrend < 300: {daily_count} matches")

if daily_count > 0:
    print("   Query: daily_supertrend_10_3 < 300")
    print("   Expected to return matches in API")

# Test weekly query
cur.execute("""
    SELECT COUNT(*)
    FROM daily_candles
    WHERE symbol = %s
    AND (indicators->>'weekly_supertrend_10_3')::numeric < 200
""", (symbol,))
weekly_count = cur.fetchone()[0]
print(f"\n2. Weekly SuperTrend < 200: {weekly_count} matches")

if weekly_count > 0:
    print("   Query: weekly_supertrend_10_3 < 200")
    print("   Expected to return matches in API")

# Test monthly query
cur.execute("""
    SELECT COUNT(*)
    FROM daily_candles
    WHERE symbol = %s
    AND (indicators->>'monthly_supertrend_10_3')::numeric > 300
""", (symbol,))
monthly_count = cur.fetchone()[0]
print(f"\n3. Monthly SuperTrend > 300: {monthly_count} matches")

if monthly_count > 0:
    print("   Query: monthly_supertrend_10_3 > 300")
    print("   Expected to return matches in API")

cur.close()
conn.close()