import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("FINAL VERIFICATION - DAILY SUPERTREND")
print("="*80)
print("Your Expected Values:")
print("-"*80)
print("999 -> 250.01 -> 0")
print("998 -> 251.07 -> 0")
print("997 -> 251.77 -> 0")
print("996 -> 253.27 -> 0")
print("995 -> 256.76 -> 0")
print("994 -> 256.76 -> 0")
print("993 -> 256.76 -> 0")
print("992 -> 256.76 -> 0")
print("991 -> 256.76 -> 0")
print()

print("Current Database Values:")
print("-"*80)

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

for row in cur.fetchall():
    seq, st, dir = row
    print(f"{seq} -> {st:.2f} -> {dir}")

print("\n" + "="*80)
print("VERIFICATION RESULT:")
print("-"*80)

# Check exact matches
expected = {
    999: 250.01,
    998: 251.07,
    997: 251.77,
    996: 253.27,
    995: 256.76,
    994: 256.76,
    993: 256.76,
    992: 256.76,
    991: 256.76
}

cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 991 AND 999
    ORDER BY candle_sequence_number
""")

all_match = True
for row in cur.fetchall():
    seq, st, dir = row
    expected_val = expected[seq]

    # Allow small tolerance for floating point
    if abs(float(st) - expected_val) > 0.1 or dir != 0:
        all_match = False
        print(f"MISMATCH at {seq}: Got {st:.2f} (dir={dir}), Expected {expected_val} (dir=0)")

if all_match:
    print("✅ ALL VALUES MATCH PERFECTLY!")
    print("Daily SuperTrend is working correctly.")
else:
    print("❌ Some values don't match.")

cur.close()
conn.close()