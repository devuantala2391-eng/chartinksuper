import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("FORCING COMPLETE RECALCULATION WITH CORRECT PROCEDURES")
print("=" * 80)

# First ensure ATR is calculated for all candles
print("\n1. Calculating ATR for all candles...")
cur.execute("SELECT * FROM calculate_atr(10, '20MICRONS')")
result = cur.fetchone()
print(f"   ATR calculation result: {result}")
conn.commit()

# Then calculate SuperTrend with the corrected procedure
print("\n2. Calculating Daily SuperTrend with corrected procedure...")
cur.execute("SELECT * FROM calculate_daily_supertrend_for_symbol('20MICRONS', 10, 3, TRUE)")
result = cur.fetchone()
print(f"   SuperTrend calculation result: {result}")
conn.commit()

# Now verify the values
print("\n3. VERIFICATION OF VALUES:")
print("-" * 80)

expected = {
    999: (250.01, 0),
    998: (251.07, 0),
    997: (251.77, 0),
    996: (253.27, 0),
    995: (256.76, 0),
    994: (256.76, 0),
    993: (256.76, 0),
    992: (256.76, 0),
    991: (256.76, 0)
}

print("Seq  | Database ST | Database Dir | Expected ST | Expected Dir | Status")
print("-----|-------------|--------------|-------------|--------------|--------")

cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 991 AND 999
    ORDER BY candle_sequence_number DESC
""")

all_correct = True
for row in cur.fetchall():
    seq, st, dir = row
    exp_st, exp_dir = expected[seq]

    if abs(float(st) - exp_st) < 0.1 and dir == exp_dir:
        status = "CORRECT"
    else:
        status = "WRONG"
        all_correct = False

    print(f"{seq:4} | {st:11.2f} | {dir:12} | {exp_st:11.2f} | {exp_dir:12} | {status}")

print("\n" + "=" * 80)
if all_correct:
    print("SUCCESS: All values now match expected values!")
    print("The SuperTrend calculation is working correctly.")
else:
    print("ERROR: Some values still don't match.")
    print("Further investigation needed.")

cur.close()
conn.close()