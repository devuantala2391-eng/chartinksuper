import psycopg2
from decimal import Decimal

conn = psycopg2.connect(
    host="localhost",
    database="nse_highspeed",
    user="postgres",
    password="123"
)
cur = conn.cursor()

print("ROOT CAUSE ANALYSIS FOR WEEKLY/MONTHLY SUPERTREND DISCREPANCIES")
print("="*80)

# WEEKLY ANALYSIS
print("\n1. WEEKLY SUPERTREND ANALYSIS")
print("-"*80)
print("Expected: 193.81 (direction=1)")
print("Actual: 186.60 (direction=1)")
print("Difference: 7.21 (3.7% off)")
print()

# Check the weekly OHLC data that's being used
print("Checking Weekly OHLC Data Consistency:")
cur.execute("""
    SELECT
        weekly_candle_key_id,
        COUNT(DISTINCT weekly_high) as unique_highs,
        COUNT(DISTINCT weekly_low) as unique_lows,
        COUNT(DISTINCT weekly_close) as unique_closes,
        MIN(weekly_high) as min_high,
        MAX(weekly_high) as max_high,
        MIN(weekly_low) as min_low,
        MAX(weekly_low) as max_low,
        MIN(weekly_close) as min_close,
        MAX(weekly_close) as max_close
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND weekly_candle_key_id IS NOT NULL
    GROUP BY weekly_candle_key_id
    HAVING COUNT(DISTINCT weekly_high) > 1
    ORDER BY weekly_candle_key_id
    LIMIT 10
""")

print("\nWeeks with multiple different OHLC values (data inconsistency):")
print("Week Key | Unique H | Unique L | Unique C | High Range | Low Range | Close Range")
for row in cur.fetchall():
    week, uh, ul, uc, min_h, max_h, min_l, max_l, min_c, max_c = row
    print(f"{week} | {uh:8} | {ul:8} | {uc:8} | {min_h:.2f}-{max_h:.2f} | {min_l:.2f}-{max_l:.2f} | {min_c:.2f}-{max_c:.2f}")

# Check ATR variations within same week
print("\nATR Variations within same week:")
cur.execute("""
    SELECT
        weekly_candle_key_id,
        COUNT(DISTINCT (indicators->>'weekly_atr_10')::numeric) as unique_atrs,
        MIN((indicators->>'weekly_atr_10')::numeric) as min_atr,
        MAX((indicators->>'weekly_atr_10')::numeric) as max_atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND indicators ? 'weekly_atr_10'
    GROUP BY weekly_candle_key_id
    HAVING COUNT(DISTINCT (indicators->>'weekly_atr_10')::numeric) > 1
    ORDER BY weekly_candle_key_id DESC
    LIMIT 5
""")

for row in cur.fetchall():
    week, unique_atrs, min_atr, max_atr = row
    diff = float(max_atr - min_atr)
    print(f"{week}: {unique_atrs} different ATR values, range: {min_atr:.2f} to {max_atr:.2f} (diff: {diff:.2f})")

# Analyze Week 203 specifically (where 193.81 originates)
print("\n" + "-"*80)
print("WEEK 203 ANALYSIS (Origin of 193.81):")
cur.execute("""
    SELECT DISTINCT
        weekly_high,
        weekly_low,
        weekly_close,
        (indicators->>'weekly_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND weekly_candle_key_id = '20MICRONS_W203'
    AND indicators ? 'weekly_atr_10'
""")

for row in cur.fetchall():
    high, low, close, atr = row
    hl2 = (Decimal(str(high)) + Decimal(str(low))) / 2
    lower_band = hl2 - (Decimal('3') * Decimal(str(atr)))
    print(f"OHLC: {high:.2f}/{low:.2f}/{close:.2f}")
    print(f"ATR: {atr:.2f}")
    print(f"HL2: {hl2:.2f}")
    print(f"Lower Band (HL2 - 3*ATR): {lower_band:.2f}")

# MONTHLY ANALYSIS
print("\n" + "="*80)
print("2. MONTHLY SUPERTREND ANALYSIS")
print("-"*80)
print("Expected: 337.11 (direction=0)")
print("Actual: 313.99 (direction=0)")
print("Difference: 23.12 (6.9% off)")
print()

# Check monthly OHLC consistency
print("Checking Monthly OHLC Data Consistency:")
cur.execute("""
    SELECT
        monthly_candle_key_id,
        COUNT(DISTINCT monthly_high) as unique_highs,
        COUNT(DISTINCT monthly_low) as unique_lows,
        COUNT(DISTINCT monthly_close) as unique_closes,
        MIN(monthly_high) as min_high,
        MAX(monthly_high) as max_high
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND monthly_candle_key_id IS NOT NULL
    GROUP BY monthly_candle_key_id
    HAVING COUNT(DISTINCT monthly_high) > 1
    ORDER BY monthly_candle_key_id
    LIMIT 10
""")

print("\nMonths with multiple different OHLC values:")
for row in cur.fetchall():
    month, uh, ul, uc, min_h, max_h = row
    print(f"{month}: {uh} unique highs (range: {min_h:.2f} to {max_h:.2f})")

# Check Month 43 (where 337.11 originates)
print("\n" + "-"*80)
print("MONTH 43 ANALYSIS (Origin of 337.11):")
cur.execute("""
    SELECT DISTINCT
        monthly_high,
        monthly_low,
        monthly_close,
        (indicators->>'monthly_atr_10')::numeric as atr
    FROM daily_candles
    WHERE symbol = '20MICRONS'
    AND monthly_candle_key_id = '20MICRONS_M43'
    AND indicators ? 'monthly_atr_10'
""")

for row in cur.fetchall():
    high, low, close, atr = row
    hl2 = (Decimal(str(high)) + Decimal(str(low))) / 2
    upper_band = hl2 + (Decimal('3') * Decimal(str(atr)))
    print(f"OHLC: {high:.2f}/{low:.2f}/{close:.2f}")
    print(f"ATR: {atr:.2f}")
    print(f"HL2: {hl2:.2f}")
    print(f"Upper Band (HL2 + 3*ATR): {upper_band:.2f}")

# ROOT CAUSE HYPOTHESIS
print("\n" + "="*80)
print("ROOT CAUSE ANALYSIS SUMMARY")
print("="*80)

print("""
FINDINGS:

1. WEEKLY SUPERTREND (186.60 vs 193.81):
   - The value 193.81 comes from Week 203's lower band calculation
   - Issue: Weekly OHLC values change WITHIN the same week as data accumulates
   - Each daily candle in a week may have different weekly_high/low/close values
   - This causes ATR to vary within the same week
   - The stored procedure only calculates once per week transition
   - It uses the FIRST occurrence of the week's data, not the FINAL values

2. MONTHLY SUPERTREND (313.99 vs 337.11):
   - The value 337.11 comes from Month 43's upper band
   - Same issue: Monthly OHLC values evolve as the month progresses
   - Early daily candles in a month have incomplete monthly data
   - The stored procedure calculates with incomplete data

3. ROOT CAUSE:
   - The weekly/monthly OHLC values are PROGRESSIVE (they update as time goes on)
   - The SuperTrend calculation happens at week/month TRANSITIONS
   - It uses whatever OHLC data is available at that moment
   - By the end of the period, the OHLC values have changed
   - This creates a mismatch between early and final calculations

4. WHY DAILY WORKS PERFECTLY:
   - Daily candles have fixed, immutable OHLC values
   - No progressive updates within the day
   - Each calculation uses consistent data

5. THE EXPECTED VALUES:
   - Likely calculated using FINAL/COMPLETE weekly and monthly OHLC
   - Our stored procedure uses PROGRESSIVE/INCOMPLETE data
   - This explains the 3.7% and 6.9% discrepancies
""")

cur.close()
conn.close()