import psycopg2
import json

def test_weekly_atr():
    """Test weekly ATR calculation and compare with expected values"""
    try:
        # Connect to database
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # First, check what symbol we have and what weekly candles exist
        print("=== Checking Weekly Candles Data ===")
        cur.execute("""
            SELECT week_sequence_number, high, low, close,
                   LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close
            FROM weekly_candles
            WHERE symbol = '20MICRONS'
            AND week_sequence_number BETWEEN 195 AND 200
            ORDER BY week_sequence_number
        """)

        print("Weekly candles around target weeks:")
        print("Week# | High    | Low     | Close   | Prev Close | TR")
        print("-" * 70)
        for row in cur.fetchall():
            week_num, high, low, close, prev_close = row
            if prev_close:
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                print(f"{week_num:5} | {high:7.2f} | {low:7.2f} | {close:7.2f} | {prev_close:10.2f} | {tr:6.2f}")
            else:
                print(f"{week_num:5} | {high:7.2f} | {low:7.2f} | {close:7.2f} | {'N/A':^10} | N/A")

        # Check which daily candles map to which weeks
        print("\n=== Daily Candles to Week Mapping ===")
        cur.execute("""
            SELECT candle_sequence_number,
                   ((candle_sequence_number - 1) / 5) + 1 as week_num,
                   high, low, close
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number IN (992, 997, 999)
            ORDER BY candle_sequence_number
        """)

        print("Candle# | Week# | High    | Low     | Close")
        print("-" * 50)
        for row in cur.fetchall():
            print(f"{row[0]:7} | {row[1]:5} | {row[2]:7.2f} | {row[3]:7.2f} | {row[4]:7.2f}")

        # Calculate ATR manually for verification
        print("\n=== Manual ATR Calculation (Period=10) ===")
        cur.execute("""
            WITH weekly_tr AS (
                SELECT week_sequence_number,
                       high, low, close,
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
            SELECT week_sequence_number, true_range
            FROM weekly_tr
            WHERE week_sequence_number BETWEEN 190 AND 200
            AND true_range IS NOT NULL
            ORDER BY week_sequence_number
        """)

        tr_data = cur.fetchall()
        print("Week# | True Range")
        print("-" * 25)
        for week_num, tr in tr_data:
            if tr:
                print(f"{week_num:5} | {tr:10.2f}")

        # Now test the function
        print("\n=== Testing calculate_weekly_atr function ===")

        # Clear existing weekly ATR values
        cur.execute("""
            UPDATE daily_candles
            SET indicators = indicators - 'weekly_atr_10'
            WHERE symbol = '20MICRONS'
        """)
        conn.commit()

        # Run the function
        cur.execute("SELECT * FROM calculate_weekly_atr(10, '20MICRONS')")
        result = cur.fetchone()
        print(f"Function result: {result}")

        # Check the results
        cur.execute("""
            SELECT candle_sequence_number, (indicators->>'weekly_atr_10')::numeric as weekly_atr_10
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number IN (992, 997, 999)
            ORDER BY candle_sequence_number
        """)

        print("\nActual vs Expected:")
        results = cur.fetchall()
        expected = {
            992: 21.49,
            997: 20.32,
            999: 18.70
        }

        for candle_num, atr_val in results:
            expected_val = expected.get(candle_num, 0)
            if atr_val:
                atr_val = float(atr_val)
                diff = atr_val - expected_val
                status = "OK" if abs(diff) < 0.1 else "FAIL"
                print(f"Candle {candle_num}: {atr_val:6.2f} (expected {expected_val:6.2f}) {status} diff={diff:+.2f}")
            else:
                print(f"Candle {candle_num}: No ATR value (expected {expected_val:6.2f}) FAIL")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_weekly_atr()