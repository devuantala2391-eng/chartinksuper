import psycopg2
import json

def check_weekly_atr():
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

        # Check if weekly ATR was calculated
        cur.execute("""
            SELECT candle_sequence_number, indicators
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number IN (997, 999)
            ORDER BY candle_sequence_number
        """)

        results = cur.fetchall()

        print("Checking weekly ATR values:")
        for seq_num, indicators in results:
            if indicators:
                if isinstance(indicators, dict):
                    indicators_dict = indicators
                else:
                    indicators_dict = json.loads(indicators)
                weekly_atr_10 = indicators_dict.get('weekly_atr_10', 'NOT FOUND')
            else:
                weekly_atr_10 = 'NOT FOUND'
            print(f"Candle {seq_num}: weekly_atr_10 = {weekly_atr_10}")

        # Also check if calculate_weekly_atr function exists
        cur.execute("""
            SELECT proname FROM pg_proc
            WHERE proname = 'calculate_weekly_atr'
        """)
        func_result = cur.fetchone()
        print(f"\nFunction calculate_weekly_atr exists: {func_result is not None}")

        # Try to run the function directly
        print("\nTesting function directly:")
        cur.execute("SELECT * FROM calculate_weekly_atr(10, '20MICRONS')")
        func_result = cur.fetchone()
        print(f"Function result: {func_result}")

        # Also check a few more candles to see the sliding window effect
        print("\nChecking more candles:")
        cur.execute("""
            SELECT candle_sequence_number, (indicators->>'weekly_atr_10')::numeric as weekly_atr_10
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number BETWEEN 995 AND 999
            ORDER BY candle_sequence_number
        """)

        more_results = cur.fetchall()
        for seq_num, atr_val in more_results:
            print(f"Candle {seq_num}: weekly_atr_10 = {atr_val}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_weekly_atr()