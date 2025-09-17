import psycopg2

def check_symbols():
    """Check what symbols are in database"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="nse_highspeed",
            user="postgres",
            password="123"
        )
        cur = conn.cursor()

        # Check all symbols in daily_candles
        cur.execute("""
            SELECT DISTINCT symbol FROM daily_candles
            ORDER BY symbol
        """)
        symbols = cur.fetchall()
        print("Symbols in daily_candles:")
        for symbol in symbols:
            print(f"  {symbol[0]}")

        # Check all symbols in weekly_candles
        cur.execute("""
            SELECT DISTINCT symbol FROM weekly_candles
            ORDER BY symbol
        """)
        symbols = cur.fetchall()
        print("\nSymbols in weekly_candles:")
        if symbols:
            for symbol in symbols:
                print(f"  {symbol[0]}")
        else:
            print("  NONE - weekly_candles is empty!")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_symbols()