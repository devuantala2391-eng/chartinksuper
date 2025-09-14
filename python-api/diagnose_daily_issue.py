import psycopg2
from decimal import Decimal

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("DIAGNOSING DAILY SUPERTREND CALCULATION ISSUE")
print("="*80)

# First, check if ATR is calculated
print("\n1. Checking ATR values:")
cur.execute("""
    SELECT
        candle_sequence_number,
        close,
        high,
        low,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 995 AND 999
    ORDER BY candle_sequence_number DESC
""")

print("Seq  | Close   | High    | Low     | ATR")
print("-----|---------|---------|---------|--------")
for row in cur.fetchall():
    seq, close, high, low, atr = row
    print(f"{seq:4} | {close:7.2f} | {high:7.2f} | {low:7.2f} | {atr}")

# Calculate ATR if missing
print("\n2. Calculating ATR...")
cur.execute("SELECT * FROM calculate_atr(10, '20MICRONS')")
result = cur.fetchone()
print(f"ATR calculation result: {result}")
conn.commit()

# Now check ATR values again
print("\n3. ATR values after calculation:")
cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 995 AND 999
    ORDER BY candle_sequence_number DESC
""")

for row in cur.fetchall():
    seq, atr = row
    print(f"Seq {seq}: ATR = {atr}")

# Manually calculate what SuperTrend should be for sequence 999
print("\n4. Manual calculation for sequence 999:")
cur.execute("""
    SELECT
        high,
        low,
        close,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number = 999
""")

row = cur.fetchone()
if row:
    high, low, close, atr = row
    high = Decimal(str(high))
    low = Decimal(str(low))
    close = Decimal(str(close))
    atr = Decimal(str(atr)) if atr else Decimal('14')  # Default if None

    hl2 = (high + low) / 2
    multiplier = Decimal('3')

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    print(f"High: {high}, Low: {low}, Close: {close}")
    print(f"HL2: {hl2:.2f}")
    print(f"ATR: {atr}")
    print(f"Basic Upper Band: {hl2:.2f} + (3 * {atr}) = {basic_upper:.2f}")
    print(f"Basic Lower Band: {hl2:.2f} - (3 * {atr}) = {basic_lower:.2f}")

    print(f"\nExpected SuperTrend: 250.01 (direction=0)")
    print(f"Actual SuperTrend: 208.63 (direction=1)")
    print(f"\nThe actual value (208.63) is closer to the lower band!")

# Check the stored procedure being used
print("\n5. Checking which SuperTrend function is being called:")
cur.execute("""
    SELECT proname
    FROM pg_proc
    WHERE proname LIKE '%supertrend%'
    AND proname LIKE '%daily%'
    ORDER BY proname
""")

print("Available daily SuperTrend functions:")
for row in cur.fetchall():
    print(f"  - {row[0]}")

# Re-run the daily SuperTrend calculation
print("\n6. Re-running daily SuperTrend calculation...")
cur.execute("SELECT * FROM calculate_daily_supertrend_for_symbol('20MICRONS', 10, 3, TRUE)")
result = cur.fetchone()
print(f"Calculation result: {result}")
conn.commit()

# Check the result again
print("\n7. Values after recalculation:")
cur.execute("""
    SELECT
        candle_sequence_number,
        close,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 995 AND 999
    ORDER BY candle_sequence_number DESC
""")

print("Seq  | Close   | SuperTrend | Dir | Expected ST | Expected Dir")
print("-----|---------|------------|-----|-------------|-------------")
expected = {
    999: (250.01, 0),
    998: (251.07, 0),
    997: (251.78, 0),
    996: (253.26, 0),
    995: (256.76, 0)
}

for row in cur.fetchall():
    seq, close, st, dir = row
    exp_st, exp_dir = expected.get(seq, (0, 0))
    match = "MATCH" if abs(float(st) - exp_st) < 0.1 else "WRONG"
    print(f"{seq:4} | {close:7.2f} | {st:10.2f} | {dir:3} | {exp_st:11.2f} | {exp_dir:12} | {match}")

cur.close()
conn.close()