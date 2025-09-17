import psycopg2

def check_weekly_candles():
    """Check weekly candles data"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # Check what symbols have weekly candles
        cur.execute("""
            SELECT symbol, COUNT(*) as count
            FROM weekly_candles
            GROUP BY symbol
        """)

        print("Weekly candles by symbol:")
        results = cur.fetchall()
        if not results:
            print("NO WEEKLY CANDLES FOUND!")
        else:
            for symbol, count in results:
                print(f"  {symbol}: {count} weeks")

        # Check daily candles count for 20MICRONS
        cur.execute("""
            SELECT COUNT(*), MIN(candle_sequence_number), MAX(candle_sequence_number)
            FROM daily_candles
            WHERE symbol = '20MICRONS'
        """)
        count, min_seq, max_seq = cur.fetchone()
        print(f"\nDaily candles for 20MICRONS: {count} candles (seq {min_seq} to {max_seq})")

        # Check if we have weekly_close populated in daily_candles
        cur.execute("""
            SELECT COUNT(*)
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND weekly_close IS NOT NULL
        """)
        weekly_close_count = cur.fetchone()[0]
        print(f"Daily candles with weekly_close populated: {weekly_close_count}")

        # Check a few daily candles to see their structure
        cur.execute("""
            SELECT candle_sequence_number, high, low, close, weekly_high, weekly_low, weekly_close
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number IN (990, 995, 999)
            ORDER BY candle_sequence_number
        """)

        print("\nSample daily candles:")
        print("Seq#  | High    | Low     | Close   | W.High  | W.Low   | W.Close")
        print("-" * 70)
        for row in cur.fetchall():
            seq, h, l, c, wh, wl, wc = row
            wh_str = f"{wh:7.2f}" if wh else "    N/A"
            wl_str = f"{wl:7.2f}" if wl else "    N/A"
            wc_str = f"{wc:7.2f}" if wc else "    N/A"
            print(f"{seq:5} | {h:7.2f} | {l:7.2f} | {c:7.2f} | {wh_str} | {wl_str} | {wc_str}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_weekly_candles()