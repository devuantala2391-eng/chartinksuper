import psycopg2

def fix_weekly_keys():
    """Fix the weekly_candle_key_id mapping in daily_candles"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        print("Fixing weekly_candle_key_id mappings...")

        # Update daily candles to have correct weekly_candle_key_id
        # The formula should be: week_num = (candle_sequence_number / 5) + 1
        cur.execute("""
            UPDATE daily_candles dc
            SET weekly_candle_key_id =
                dc.symbol || '_W' || (((dc.candle_sequence_number) / 5) + 1)
            WHERE dc.symbol = '20MICRONS'
        """)

        rows_updated = cur.rowcount
        print(f"Updated {rows_updated} daily candles with correct weekly_candle_key_id")

        # Verify the fix
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

        print("\nVerification - Daily candles weekly key mapping:")
        print("Seq#  | Weekly Key ID      | Expected Week")
        print("-" * 50)
        for seq, key_id, exp_week in cur.fetchall():
            key_str = key_id if key_id else "NULL"
            print(f"{seq:5} | {key_str:18} | {exp_week:13}")

        # Check if joins will work now
        cur.execute("""
            SELECT COUNT(*)
            FROM daily_candles dc
            JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
            WHERE dc.symbol = '20MICRONS'
        """)

        join_count = cur.fetchone()[0]
        print(f"\nJoin test: {join_count} daily candles successfully join with weekly candles")

        conn.commit()
        cur.close()
        conn.close()

        print("\nWeekly key mapping fixed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_weekly_keys()