import psycopg2

def investigate():
    """Investigate weekly candle data structure"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # Check if weekly candles exist
        cur.execute("""
            SELECT COUNT(*), MIN(week_sequence_number), MAX(week_sequence_number)
            FROM weekly_candles
            WHERE symbol = '20MICRONS'
        """)
        count, min_week, max_week = cur.fetchone()
        print(f"Weekly candles: Count={count}, Min week={min_week}, Max week={max_week}")

        # Get all weekly candles to understand the ATR calculation
        cur.execute("""
            WITH weekly_tr AS (
                SELECT
                    week_sequence_number,
                    high,
                    low,
                    close,
                    LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close, 1) OVER (ORDER BY week_sequence_number)),
                        ABS(low - LAG(close, 1) OVER (ORDER BY week_sequence_number))
                    ) as true_range
                FROM weekly_candles
                WHERE symbol = '20MICRONS'
                ORDER BY week_sequence_number
            )
            SELECT * FROM weekly_tr
            WHERE week_sequence_number >= 190
            ORDER BY week_sequence_number
        """)

        print("\nWeekly TR Calculation:")
        print("Week# | High    | Low     | Close   | Prev Close | True Range")
        print("-" * 70)

        tr_values = []
        for row in cur.fetchall():
            week_num, high, low, close, prev_close, tr = row
            if tr:
                tr_values.append((week_num, float(tr)))
                print(f"{week_num:5} | {high:7.2f} | {low:7.2f} | {close:7.2f} | {prev_close:10.2f} | {tr:10.2f}")
            else:
                print(f"{week_num:5} | {high:7.2f} | {low:7.2f} | {close:7.2f} | {'N/A':^10} | {'N/A':^10}")

        # Manually calculate ATR using Wilder's smoothing
        print("\nManual ATR Calculation (Period=10):")
        print("Week# | True Range | ATR (10)")
        print("-" * 40)

        atr_values = []
        atr = None
        period = 10
        tr_sum = 0

        for i, (week_num, tr) in enumerate(tr_values):
            if i < period - 1:
                # Accumulate for initial SMA
                tr_sum += tr
                print(f"{week_num:5} | {tr:10.2f} | Accumulating...")
            elif i == period - 1:
                # Calculate first ATR as SMA
                tr_sum += tr
                atr = tr_sum / period
                atr_values.append((week_num, atr))
                print(f"{week_num:5} | {tr:10.2f} | {atr:10.2f} (Initial SMA)")
            else:
                # Use Wilder's smoothing
                atr = ((period - 1) * atr + tr) / period
                atr_values.append((week_num, atr))
                print(f"{week_num:5} | {tr:10.2f} | {atr:10.2f}")

        # Check what weeks correspond to our target candles
        print("\n=== Target Values Check ===")
        target_weeks = {
            199: 21.49,  # candle 992
            200: 18.70   # candles 997, 999
        }

        for week_num, expected in target_weeks.items():
            actual = next((atr for w, atr in atr_values if w == week_num), None)
            if actual:
                diff = actual - expected
                status = "CLOSE" if abs(diff) < 1 else "OFF"
                print(f"Week {week_num}: ATR={actual:.2f} (expected {expected:.2f}) {status} diff={diff:+.2f}")
            else:
                print(f"Week {week_num}: No ATR calculated (expected {expected:.2f})")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    investigate()