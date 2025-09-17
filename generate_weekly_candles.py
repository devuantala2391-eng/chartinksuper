"""
Generate weekly candles from daily candles data
This is needed because the weekly_candles table is empty
"""

import psycopg2
from datetime import datetime

def generate_weekly_candles():
    """Generate weekly candles from daily candles"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        print("Generating weekly candles from daily candles...")

        # First, create weekly candles by grouping daily candles by week
        # Assuming 5-day weeks (market days)
        cur.execute("""
            WITH weekly_groups AS (
                SELECT
                    symbol,
                    ((candle_sequence_number) / 5) as week_num,
                    MAX(high) as high,
                    MIN(low) as low,
                    FIRST_VALUE(open) OVER (
                        PARTITION BY symbol, ((candle_sequence_number) / 5)
                        ORDER BY candle_sequence_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                    ) as open,
                    LAST_VALUE(close) OVER (
                        PARTITION BY symbol, ((candle_sequence_number) / 5)
                        ORDER BY candle_sequence_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                    ) as close,
                    SUM(volume) as volume,
                    COUNT(*) as trading_days,
                    MIN(timestamp) as week_start_timestamp,
                    MAX(timestamp) as week_end_timestamp,
                    MIN(datetime) as week_start_datetime,
                    MAX(datetime) as week_end_datetime
                FROM daily_candles
                WHERE symbol = '20MICRONS'
                GROUP BY symbol, ((candle_sequence_number) / 5), candle_sequence_number, open, close
            ),
            distinct_weeks AS (
                SELECT DISTINCT ON (symbol, week_num)
                    symbol,
                    week_num + 1 as week_num,  -- Make it 1-based
                    high,
                    low,
                    open,
                    close,
                    volume,
                    trading_days,
                    week_start_timestamp,
                    week_end_timestamp,
                    week_start_datetime,
                    week_end_datetime
                FROM weekly_groups
                ORDER BY symbol, week_num, week_end_timestamp DESC
            )
            INSERT INTO weekly_candles (
                weekly_candle_key_id,
                symbol,
                week_sequence_number,
                high,
                low,
                open,
                close,
                volume,
                trading_days_count,
                week_start_timestamp,
                week_end_timestamp,
                week_start_datetime,
                week_end_datetime,
                indicators,
                created_at,
                updated_at
            )
            SELECT
                symbol || '_W' || week_num as weekly_candle_key_id,
                symbol,
                week_num as week_sequence_number,
                high,
                low,
                open,
                close,
                volume,
                trading_days as trading_days_count,
                week_start_timestamp,
                week_end_timestamp,
                week_start_datetime,
                week_end_datetime,
                '{}'::jsonb as indicators,
                CURRENT_TIMESTAMP as created_at,
                CURRENT_TIMESTAMP as updated_at
            FROM distinct_weeks
            ON CONFLICT (weekly_candle_key_id) DO NOTHING
            RETURNING week_sequence_number
        """)

        inserted = cur.fetchall()
        print(f"Inserted {len(inserted)} weekly candles")

        # Verify the weekly candles were created
        cur.execute("""
            SELECT COUNT(*), MIN(week_sequence_number), MAX(week_sequence_number)
            FROM weekly_candles
            WHERE symbol = '20MICRONS'
        """)
        count, min_week, max_week = cur.fetchone()
        print(f"Weekly candles created: {count} (weeks {min_week} to {max_week})")

        # Check sample weekly candles
        cur.execute("""
            SELECT week_sequence_number, high, low, open, close
            FROM weekly_candles
            WHERE symbol = '20MICRONS'
            AND week_sequence_number BETWEEN 195 AND 200
            ORDER BY week_sequence_number
        """)

        print("\nSample weekly candles:")
        print("Week# | High    | Low     | Open    | Close")
        print("-" * 50)
        for row in cur.fetchall():
            week, h, l, o, c = row
            print(f"{week:5} | {h:7.2f} | {l:7.2f} | {o:7.2f} | {c:7.2f}")

        conn.commit()
        cur.close()
        conn.close()

        print("\nWeekly candles generated successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_weekly_candles()