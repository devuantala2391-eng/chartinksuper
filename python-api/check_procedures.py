import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("CHECKING STORED PROCEDURES")
print("=" * 80)

# Check which SuperTrend procedures exist
cur.execute("""
    SELECT proname
    FROM pg_proc
    WHERE proname LIKE '%supertrend%'
    ORDER BY proname
""")

print("\nSuperTrend procedures found:")
print("-" * 80)
for row in cur.fetchall():
    print(f"  - {row[0]}")

# Check if calculate_timeframe_supertrend exists
cur.execute("""
    SELECT proname
    FROM pg_proc
    WHERE proname = 'calculate_timeframe_supertrend'
""")

if cur.fetchone():
    print("\nWARNING: calculate_timeframe_supertrend EXISTS")
    print("This is likely the OLD/WRONG procedure being called!")
else:
    print("\ncalculate_timeframe_supertrend NOT found")

# Check for our correct procedure
cur.execute("""
    SELECT proname
    FROM pg_proc
    WHERE proname = 'calculate_daily_supertrend_for_symbol'
""")

if cur.fetchone():
    print("\nGOOD: calculate_daily_supertrend_for_symbol EXISTS")
    print("This is the CORRECT procedure that should be used!")
else:
    print("\ncalculate_daily_supertrend_for_symbol NOT found")

cur.close()
conn.close()