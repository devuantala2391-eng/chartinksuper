import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("CHECKING ACTUAL DATABASE VALUES FOR DAILY SUPERTREND")
print("="*80)

# Check what's in sequence 999, 199, etc
print("\nChecking various sequence numbers:")
sequences_to_check = [999, 998, 997, 996, 995, 199, 198, 197, 196, 195]

cur.execute("""
    SELECT
        candle_sequence_number,
        symbol,
        close,
        high,
        low,
        (indicators->>'daily_supertrend_10_3')::numeric as supertrend,
        (indicators->>'daily_supertrend_10_3_direction')::integer as direction,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE candle_sequence_number = ANY(%s)
    ORDER BY candle_sequence_number DESC
""", (sequences_to_check,))

print("\nSeq  | Symbol     | Close   | High    | Low     | SuperTrend | Dir | ATR")
print("-----|------------|---------|---------|---------|------------|-----|-------")
for row in cur.fetchall():
    seq, sym, close, high, low, st, dir, atr = row
    print(f"{seq:4} | {sym:10} | {close:7.2f} | {high:7.2f} | {low:7.2f} | {st:10.2f} | {dir:3} | {atr}")

# Check what symbol we have data for
print("\n" + "="*80)
print("Checking what symbols are in database:")
cur.execute("""
    SELECT symbol, COUNT(*) as count, MIN(candle_sequence_number) as min_seq, MAX(candle_sequence_number) as max_seq
    FROM daily_candles
    GROUP BY symbol
""")

for row in cur.fetchall():
    symbol, count, min_seq, max_seq = row
    print(f"Symbol: {symbol}, Count: {count}, Sequences: {min_seq} to {max_seq}")

# Check sequence 999 specifically
print("\n" + "="*80)
print("EXPECTED vs ACTUAL for sequence 999:")
print("-"*80)

cur.execute("""
    SELECT
        symbol,
        candle_sequence_number,
        close,
        (indicators->>'daily_supertrend_10_3')::numeric as supertrend,
        (indicators->>'daily_supertrend_10_3_direction')::integer as direction
    FROM daily_candles
    WHERE candle_sequence_number = 999
""")

row = cur.fetchone()
if row:
    symbol, seq, close, st, dir = row
    print(f"Symbol: {symbol}")
    print(f"Sequence: {seq}")
    print(f"Close: {close}")
    print(f"ACTUAL   SuperTrend: {st}, Direction: {dir}")
    print(f"EXPECTED SuperTrend: 250.01, Direction: 0")

    if abs(float(st) - 250.01) > 1:
        print("\n❌ VALUES DO NOT MATCH!")
        print(f"Difference: {abs(float(st) - 250.01):.2f}")
else:
    print("No data found for sequence 999")

# Let's check sequence 199 too
print("\n" + "="*80)
print("Checking sequence 199 (what you mentioned):")
cur.execute("""
    SELECT
        symbol,
        candle_sequence_number,
        close,
        high,
        low,
        (indicators->>'daily_supertrend_10_3')::numeric as supertrend,
        (indicators->>'daily_supertrend_10_3_direction')::integer as direction,
        (indicators->>'daily_atr_10')::numeric as atr
    FROM daily_candles
    WHERE candle_sequence_number = 199
""")

row = cur.fetchone()
if row:
    symbol, seq, close, high, low, st, dir, atr = row
    print(f"Symbol: {symbol}")
    print(f"Sequence: {seq}")
    print(f"OHLC: H={high:.2f}, L={low:.2f}, C={close:.2f}")
    print(f"ATR: {atr}")
    print(f"SuperTrend: {st}, Direction: {dir}")
    print(f"You mentioned: 208.63, direction 1")

cur.close()
conn.close()