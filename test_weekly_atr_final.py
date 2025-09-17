import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='nse_highspeed',
    user='postgres',
    password='123'
)
cur = conn.cursor()

# Drop and recreate the function
cur.execute('DROP FUNCTION IF EXISTS calculate_weekly_atr(INTEGER, TEXT) CASCADE')
conn.commit()

# Read and execute the SQL file
with open('python-api/sql/stored_procedures/calculate_atr.sql', 'r') as f:
    sql_content = f.read()
    # Find the CREATE OR REPLACE FUNCTION for weekly ATR
    func_start = sql_content.find('CREATE OR REPLACE FUNCTION calculate_weekly_atr')
    func_end = sql_content.find('-- =====================================================\n-- MONTHLY ATR CALCULATION')
    if func_start != -1 and func_end != -1:
        # Extract just the function definition
        weekly_atr_sql = sql_content[func_start:func_end].rstrip()
        cur.execute(weekly_atr_sql)
        conn.commit()

# Clear existing values first
cur.execute("""
    UPDATE daily_candles
    SET indicators = indicators - 'weekly_atr_14'
    WHERE symbol = '20MICRONS'
""")
conn.commit()

# Test the function
cur.execute("SELECT * FROM calculate_weekly_atr(14, '20MICRONS')")
result = cur.fetchone()
print(f'Function executed: {result[1]} rows updated, status: {result[3]}')

# Check the actual values
cur.execute("""
    SELECT
        candle_sequence_number,
        indicators->'weekly_atr_14' as atr_value
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND candle_sequence_number IN (999, 997, 992)
    ORDER BY candle_sequence_number DESC
""")

print('\nRESULTS:')
print('Seq# | Actual  | Expected | Match?')
print('-' * 40)
expected = {999: 18.70, 997: 20.32, 992: 21.49}
for seq, atr_val in cur.fetchall():
    exp = expected[seq]
    match = 'YES' if float(atr_val) == exp else 'NO'
    print(f'{seq:4} | {float(atr_val):7.2f} | {exp:8.2f} | {match}')

cur.close()
conn.close()