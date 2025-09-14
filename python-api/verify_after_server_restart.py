"""
INSTRUCTIONS:
1. Start server with run_server.bat
2. Hit the hard-refresh curl
3. Hit the query curl
4. Run this script to verify values in database
"""

import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("VERIFYING VALUES AFTER SERVER RESTART AND HARD REFRESH")
print("=" * 80)

# Check the actual values in database
cur.execute("""
    SELECT
        candle_sequence_number,
        close,
        (indicators->>'daily_supertrend_10_3')::numeric as st,
        (indicators->>'daily_supertrend_10_3_direction')::integer as dir
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number BETWEEN 991 AND 999
    ORDER BY candle_sequence_number DESC
""")

expected = {
    999: (250.01, 0),
    998: (251.07, 0),
    997: (251.77, 0),
    996: (253.27, 0),
    995: (256.76, 0),
    994: (256.76, 0),
    993: (256.76, 0),
    992: (256.76, 0),
    991: (256.76, 0)
}

print("Seq  | Close   | SuperTrend | Dir | Expected ST | Expected Dir | Status")
print("-----|---------|------------|-----|-------------|--------------|--------")

all_correct = True
for row in cur.fetchall():
    seq, close, st, dir = row
    if seq in expected:
        exp_st, exp_dir = expected[seq]

        if st and abs(float(st) - exp_st) < 0.1 and dir == exp_dir:
            status = "CORRECT"
        else:
            status = "WRONG"
            all_correct = False

        st_str = f"{st:.2f}" if st else "NONE"
        print(f"{seq:4} | {close:7.2f} | {st_str:10} | {dir:3} | {exp_st:11.2f} | {exp_dir:12} | {status}")

print("\n" + "=" * 80)

if all_correct:
    print("SUCCESS: All values are correct!")
    print("The fix is working properly after server restart and hard refresh.")
else:
    print("ISSUE: Some values are still incorrect.")
    print("")
    print("If you're still seeing old values (208.63), please:")
    print("1. Restart the server completely")
    print("2. Make sure the migration runs (check server logs)")
    print("3. Run hard-refresh API call")
    print("4. Check this script again")

cur.close()
conn.close()