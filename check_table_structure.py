import psycopg2

def check_table_structure():
    """Check weekly_candles table structure"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # Check weekly_candles columns
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'weekly_candles'
            ORDER BY ordinal_position
        """)

        print("weekly_candles table structure:")
        for col_name, data_type, is_nullable in cur.fetchall():
            nullable = "NULL" if is_nullable == 'YES' else "NOT NULL"
            print(f"  {col_name:<30} {data_type:<20} {nullable}")

        # Check daily_candles to understand how datetime columns are set
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'daily_candles'
            AND column_name LIKE '%datetime%'
            ORDER BY ordinal_position
        """)

        print("\ndaily_candles datetime columns:")
        for col_name, data_type, is_nullable in cur.fetchall():
            nullable = "NULL" if is_nullable == 'YES' else "NOT NULL"
            print(f"  {col_name:<30} {data_type:<20} {nullable}")

        # Check what's in daily_candles datetime columns
        cur.execute("""
            SELECT datetime
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            LIMIT 5
        """)

        print("\nSample datetime values from daily_candles:")
        for row in cur.fetchall():
            print(f"  {row[0]}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_table_structure()