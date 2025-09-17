import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='nse_highspeed',
    user='postgres',
    password='123'
)
cur = conn.cursor()

# Get the weekly keys that daily candles reference
cur.execute("""
    SELECT DISTINCT weekly_candle_key_id
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND weekly_candle_key_id IS NOT NULL
    ORDER BY weekly_candle_key_id
""")

weekly_keys = [row[0] for row in cur.fetchall()]
print(f"Found {len(weekly_keys)} unique weekly keys in daily candles")

# For each weekly key, create a weekly candle using daily data
for i, weekly_key in enumerate(weekly_keys):
    # Extract week number from key (e.g., '20MICRONS_W200' -> 200)
    week_num = int(weekly_key.split('_W')[1])

    # Get OHLC data for this week from daily candles
    cur.execute("""
        SELECT
            MAX(high) as week_high,
            MIN(low) as week_low,
            (SELECT open FROM daily_candles
             WHERE symbol = '20MICRONS'
             AND weekly_candle_key_id = %s
             ORDER BY candle_sequence_number ASC LIMIT 1) as week_open,
            (SELECT close FROM daily_candles
             WHERE symbol = '20MICRONS'
             AND weekly_candle_key_id = %s
             ORDER BY candle_sequence_number DESC LIMIT 1) as week_close,
            COUNT(*) as day_count
        FROM daily_candles
        WHERE symbol = '20MICRONS'
        AND weekly_candle_key_id = %s
    """, (weekly_key, weekly_key, weekly_key))

    week_data = cur.fetchone()
    if week_data and week_data[0]:  # If we have data
        high, low, open_price, close, day_count = week_data

        # Insert weekly candle
        cur.execute("""
            INSERT INTO weekly_candles
            (weekly_candle_key_id, symbol, week_sequence_number, high, low, open, close, volume, datetime, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (weekly_candle_key_id) DO UPDATE SET
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                open = EXCLUDED.open,
                close = EXCLUDED.close,
                updated_at = NOW()
        """, (
            weekly_key,
            '20MICRONS',
            week_num,
            high,
            low,
            open_price,
            close,
            0,  # volume
            None  # datetime
        ))

        print(f"Created weekly candle {weekly_key}: H={high:.2f}, L={low:.2f}, O={open_price:.2f}, C={close:.2f}")

conn.commit()

# Verify creation
cur.execute("""
    SELECT COUNT(*) FROM weekly_candles WHERE symbol = '20MICRONS'
""")
count = cur.fetchone()[0]
print(f"\nTotal weekly candles created: {count}")

# Check specific weeks for our test candles
cur.execute("""
    SELECT
        weekly_candle_key_id,
        week_sequence_number,
        high,
        low,
        close
    FROM weekly_candles
    WHERE symbol = '20MICRONS'
    AND weekly_candle_key_id IN ('20MICRONS_W209', '20MICRONS_W210')
    ORDER BY week_sequence_number
""")

print("\nTest weekly candles:")
for key, seq, h, l, c in cur.fetchall():
    print(f"{key}: seq={seq}, H={h:.2f}, L={l:.2f}, C={c:.2f}")

cur.close()
conn.close()