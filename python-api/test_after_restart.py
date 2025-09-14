import psycopg2
import requests
import time

print("TESTING SUPERTREND VALUES AFTER SERVER RESTART")
print("=" * 80)

# First check current database values
conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("\n1. CURRENT DATABASE VALUES (before API call):")
print("-" * 80)

cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number = 999
""")

row = cur.fetchone()
if row:
    seq, st, dir = row
    print(f"Seq {seq}: SuperTrend={st:.2f}, Direction={dir}")
    print(f"Expected: SuperTrend=250.01, Direction=0")

    if abs(float(st) - 250.01) < 0.1:
        print("STATUS: CORRECT VALUE")
    else:
        print(f"STATUS: WRONG VALUE (off by {abs(float(st) - 250.01):.2f})")

# Test with API call
print("\n2. TESTING WITH API CALL:")
print("-" * 80)
print("Making API call to refresh indicators...")

try:
    # Make the API call
    response = requests.get("http://localhost:5000/api/refresh-indicators?symbol=20MICRONS")
    if response.status_code == 200:
        print("API call successful")

        # Wait a moment for processing
        time.sleep(2)

        # Check values again
        print("\n3. DATABASE VALUES AFTER API CALL:")
        print("-" * 80)

        cur.execute("""
            SELECT
                candle_sequence_number,
                (indicators->>'daily_supertrend_10_3')::numeric as st,
                (indicators->>'daily_supertrend_10_3_direction')::integer as dir
            FROM daily_candles
            WHERE symbol = '20MICRONS'
            AND candle_sequence_number = 999
        """)

        row = cur.fetchone()
        if row:
            seq, st, dir = row
            print(f"Seq {seq}: SuperTrend={st:.2f}, Direction={dir}")
            print(f"Expected: SuperTrend=250.01, Direction=0")

            if abs(float(st) - 250.01) < 0.1:
                print("STATUS: VALUES REMAIN CORRECT AFTER API CALL")
            else:
                print(f"STATUS: API CALL BROKE THE VALUES (now {st:.2f} instead of 250.01)")
    else:
        print(f"API call failed with status {response.status_code}")
except Exception as e:
    print(f"Note: Server might not be running. Start with run_server.py to test API")
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("FINAL STATUS:")
print("-" * 80)

# Final check
cur.execute("""
    SELECT
        candle_sequence_number,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 997 AND 999
    ORDER BY candle_sequence_number DESC
""")

all_correct = True
expected = {
    999: 250.01,
    998: 251.07,
    997: 251.77
}

for row in cur.fetchall():
    seq, st, dir = row
    exp_st = expected[seq]
    if abs(float(st) - exp_st) > 0.1:
        all_correct = False
        print(f"Seq {seq}: {st:.2f} (expected {exp_st:.2f}) - WRONG")
    else:
        print(f"Seq {seq}: {st:.2f} (expected {exp_st:.2f}) - CORRECT")

if all_correct:
    print("\nSUCCESS: The fix is working correctly!")
    print("The migration service now includes calculate_supertrend.sql")
    print("Values persist correctly across server restarts")
else:
    print("\nISSUE: Values are still not correct")
    print("Further investigation needed")

cur.close()
conn.close()