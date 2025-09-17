import psycopg2

def check_weekly_keys():
    """Check weekly candle key relationships"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # Check if daily candles have weekly_candle_key_id
        cur.execute("""
            SELECT
                candle_sequence_number,
                weekly_candle_key_id,
                ((candle_sequence_number) / 5) + 1 as expected_week
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number IN (990, 992, 995, 997, 999)
            ORDER BY candle_sequence_number
        """)

        print("Daily candles weekly key mapping:")
        print("Seq#  | Weekly Key ID      | Expected Week")
        print("-" * 50)
        for seq, key_id, exp_week in cur.fetchall():
            key_str = key_id if key_id else "NULL"
            print(f"{seq:5} | {key_str:18} | {exp_week:13}")

        # Check if the weekly candles exist
        cur.execute("""
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                high,
                low,
                close
            FROM weekly_candles
            WHERE symbol = '20MICRONS'
            AND week_sequence_number BETWEEN 198 AND 200
            ORDER BY week_sequence_number
        """)

        print("\nWeekly candles:")
        print("Key ID              | Week# | High    | Low     | Close")
        print("-" * 60)
        for key_id, week_num, high, low, close in cur.fetchall():
            print(f"{key_id:19} | {week_num:5} | {high:7.2f} | {low:7.2f} | {close:7.2f}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_weekly_keys()