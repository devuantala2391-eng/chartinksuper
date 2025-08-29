# Core Dynamic Sliding Window Indicator System

## Overview
This document explains the core dynamic sliding window approach used for all indicator calculations in our system. This pattern ensures consistent, efficient, and mathematically correct indicator calculations across all timeframes.

## Fundamental Concept

The **Dynamic Sliding Window** approach means that each individual data point (daily candle) within a period gets its own unique calculation result, creating a "sliding window" effect where the calculation dynamically expands as the period progresses.

There are **TWO types** of Dynamic Sliding Window calculations:

### Type 1: Comparative Indicators (e.g., Percentage Change)
Each day compares itself to a reference point from a previous period.

**❌ Traditional Approach (Block-based):**
```
Week 42: All days show same weekly % = 2.50%
  Monday: 2.50%    (uses week's final close vs previous week)
  Tuesday: 2.50%   (uses week's final close vs previous week)
  Wednesday: 2.50% (uses week's final close vs previous week)
```

**✅ Dynamic Sliding Window (Comparative):**
```
Week 42: Each day shows different weekly %
  Monday: 1.61%    (Monday close vs previous week final close)
  Tuesday: 3.83%   (Tuesday close vs previous week final close) 
  Wednesday: 2.50% (Wednesday close vs previous week final close)
```

### Type 2: Cumulative Indicators (e.g., Volume)
Each day accumulates values from the start of the current period up to that day.

**❌ Traditional Approach (Block-based):**
```
Week 42: All days show same weekly volume = 1,500,000
  Monday: 1,500,000    (uses entire week's total volume)
  Tuesday: 1,500,000   (uses entire week's total volume)
  Wednesday: 1,500,000 (uses entire week's total volume)
```

**✅ Dynamic Sliding Window (Cumulative):**
```
Week 42: Each day shows progressive weekly volume accumulation
  Monday: 400,000      (Monday's volume only)
  Tuesday: 800,000     (Monday + Tuesday volumes)
  Wednesday: 1,200,000 (Monday + Tuesday + Wednesday volumes)
```

## Mathematical Formulas

### Type 1: Comparative Indicators (Percentage Change)
```
Indicator_Value = (Current_Day_Value - Reference_Period_Final_Value) / Reference_Period_Final_Value * 100
```

Where:
- `Current_Day_Value`: The value of the specific day being calculated
- `Reference_Period_Final_Value`: The final value of the reference period (previous week/month)

### Type 2: Cumulative Indicators (Volume, etc.)
```
Indicator_Value = SUM(Daily_Values_From_Period_Start_To_Current_Day)
```

Where:
- `Daily_Values_From_Period_Start_To_Current_Day`: All daily values from the start of the current period up to and including the current day

## Implemented Examples

### Type 1: Comparative Indicators

#### 1. Weekly Percentage Change
```sql
-- Each daily candle compares its close to previous week's final close
SELECT 
    dc.close as current_day_close,
    wc_prev.close as prev_week_final_close,
    ROUND(((dc.close - wc_prev.close) / wc_prev.close * 100)::numeric, 4) as weekly_pct_change
FROM daily_candles dc
LEFT JOIN weekly_candles wc_current ON dc.weekly_candle_key_id = wc_current.weekly_candle_key_id
LEFT JOIN weekly_candles wc_prev ON wc_prev.symbol = dc.symbol 
    AND wc_prev.week_sequence_number = (wc_current.week_sequence_number - 1)
```

#### 2. Monthly Percentage Change
```sql
-- Each daily candle compares its close to previous month's final close
SELECT 
    dc.close as current_day_close,
    mc_prev.close as prev_month_final_close,
    ROUND(((dc.close - mc_prev.close) / mc_prev.close * 100)::numeric, 4) as monthly_pct_change
FROM daily_candles dc
LEFT JOIN monthly_candles mc_current ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
LEFT JOIN monthly_candles mc_prev ON mc_prev.symbol = dc.symbol 
    AND mc_prev.month_sequence_number = (mc_current.month_sequence_number - 1)
```

### Type 2: Cumulative Indicators

#### 3. Weekly Volume
```sql
-- Each daily candle sums volumes from week start up to current day
SELECT 
    dc.candle_key_id,
    SUM(dc_week.volume) as weekly_volume_cumulative
FROM daily_candles dc
LEFT JOIN weekly_candles wc_current ON dc.weekly_candle_key_id = wc_current.weekly_candle_key_id
LEFT JOIN daily_candles dc_week ON dc_week.weekly_candle_key_id = wc_current.weekly_candle_key_id
    AND dc_week.datetime <= dc.datetime  -- Only sum up to current day
WHERE dc.symbol = 'STOCK_SYMBOL'
GROUP BY dc.candle_key_id
```

#### 4. Monthly Volume  
```sql
-- Each daily candle sums volumes from month start up to current day
SELECT 
    dc.candle_key_id,
    SUM(dc_month.volume) as monthly_volume_cumulative
FROM daily_candles dc
LEFT JOIN monthly_candles mc_current ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
LEFT JOIN daily_candles dc_month ON dc_month.monthly_candle_key_id = mc_current.monthly_candle_key_id
    AND dc_month.datetime <= dc.datetime  -- Only sum up to current day
WHERE dc.symbol = 'STOCK_SYMBOL'
GROUP BY dc.candle_key_id
```

## Real Data Examples

### Type 1: Comparative Indicators (Weekly Percentage)

**Stock: 20MICRONS, Week 43 (August 2025)**

Previous Week 42 Final Close: 234.36

Dynamic Sliding Window Results:
```
2025-08-25: close=233.56 → weekly%= (233.56-234.36)/234.36 = -0.34%
2025-08-26: close=228.91 → weekly%= (228.91-234.36)/234.36 = -2.33%
2025-08-28: close=230.57 → weekly%= (230.57-234.36)/234.36 = -1.62%
```

Each day within Week 43 has a **different** weekly percentage, all comparing against the same reference (234.36).

### Type 2: Cumulative Indicators (Weekly Volume)

**Stock: 20MICRONS, Week 43 (August 2025)**

Daily Volume Data:
```
2025-08-25 (Monday):    volume=500,000
2025-08-26 (Tuesday):   volume=300,000  
2025-08-28 (Wednesday): volume=750,000
```

Dynamic Sliding Window Results:
```
2025-08-25: weekly_volume = 500,000              (Monday only)
2025-08-26: weekly_volume = 800,000              (Monday + Tuesday)
2025-08-28: weekly_volume = 1,550,000            (Monday + Tuesday + Wednesday)
```

Each day within Week 43 shows **progressive accumulation** of volume from the week start.

## Database Schema Requirements

### 1. Linkage Columns
Every `daily_candles` record must have:
```sql
-- For weekly calculations
weekly_candle_key_id VARCHAR  -- Links to weekly_candles.weekly_candle_key_id

-- For monthly calculations  
monthly_candle_key_id VARCHAR -- Links to monthly_candles.monthly_candle_key_id
```

### 2. Sequence Numbers
Reference period tables must have:
```sql
-- weekly_candles table
week_sequence_number INTEGER  -- Incremental: 1, 2, 3, 4...

-- monthly_candles table
month_sequence_number INTEGER -- Incremental: 1, 2, 3, 4...
```

### 3. Indicator Storage
Results stored in JSONB column:
```sql
-- daily_candles.indicators
{
  "daily_pctchg": 1.25,
  "weekly_pctchg": -2.33,
  "monthly_pctchg": 4.56,
  "weekly_volume": 1550000,
  "monthly_volume": 8750000
}
```

## Stored Procedure Pattern

### Template Structure
```sql
CREATE OR REPLACE FUNCTION calculate_[TIMEFRAME]_[INDICATOR](
    p_symbol TEXT
) RETURNS TABLE (
    updated_rows INTEGER,
    status TEXT
) AS $$
DECLARE
    v_updated_rows INTEGER := 0;
BEGIN
    WITH indicator_data AS (
        SELECT 
            dc.candle_key_id,
            dc.close as current_close,
            ref_period.close as reference_close,
            CASE 
                WHEN ref_period.close IS NOT NULL AND ref_period.close > 0 THEN
                    ROUND(([CALCULATION_FORMULA])::numeric, 4)
                ELSE 
                    NULL
            END as indicator_value
        FROM daily_candles dc
        LEFT JOIN [current_period_table] cur_period 
            ON dc.[period]_candle_key_id = cur_period.[period]_candle_key_id
        LEFT JOIN [reference_period_table] ref_period 
            ON ref_period.symbol = dc.symbol 
            AND ref_period.[period]_sequence_number = (cur_period.[period]_sequence_number - 1)
        WHERE dc.symbol = p_symbol
          AND cur_period.[period]_sequence_number > 1  -- Skip first period
    )
    UPDATE daily_candles AS target_table
    SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || 
                     jsonb_build_object('[indicator_key]', ind.indicator_value),
        updated_at = CURRENT_TIMESTAMP
    FROM indicator_data ind
    WHERE target_table.candle_key_id = ind.candle_key_id
      AND ind.indicator_value IS NOT NULL
      AND (
          -- Only update if indicator doesn't exist or is null
          NOT (target_table.indicators ? '[indicator_key]') OR 
          (target_table.indicators->'[indicator_key]') IS NULL OR
          (target_table.indicators->'[indicator_key]') = 'null'::jsonb
      );
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    RETURN QUERY SELECT v_updated_rows, 'SUCCESS'::TEXT;
EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT 0, format('ERROR: %s', SQLERRM)::TEXT;
END;
$$ LANGUAGE plpgsql;
```

## Critical Implementation Rules

### 1. Reference Period Selection
- **Weekly**: Compare to previous week's final close (`week_sequence_number - 1`)
- **Monthly**: Compare to previous month's final close (`month_sequence_number - 1`)  
- **Quarterly**: Compare to previous quarter's final close (`quarter_sequence_number - 1`)

### 2. Skip First Periods
Always exclude the very first period since there's no reference:
```sql
WHERE cur_period.[period]_sequence_number > 1  -- Skip sequence 0 or 1
```

### 3. Null Handling
```sql
CASE 
    WHEN ref_period.close IS NOT NULL AND ref_period.close > 0 THEN
        -- Calculate indicator
    ELSE 
        NULL  -- Cannot calculate without reference
END
```

### 4. Recalculation Prevention
Only update indicators that don't exist:
```sql
WHERE (
    NOT (target_table.indicators ? 'indicator_key') OR 
    (target_table.indicators->'indicator_key') IS NULL OR
    (target_table.indicators->'indicator_key') = 'null'::jsonb
)
```

## Edge Cases to Handle

### 1. First Period of Symbol
- Week 1 or Month 1 will have NULL indicators (no previous period)
- This is mathematically correct - don't try to force a value

### 2. Missing Reference Data
- If previous period data doesn't exist, indicator should be NULL
- Don't substitute with alternative periods

### 3. Zero Division
- Always check `reference_close > 0` before division
- Return NULL if reference close is zero or negative

### 4. Data Type Precision
- Use `ROUND(...::numeric, 4)` for consistent precision
- Store as numbers, not strings in JSONB

## Service Integration Pattern

### PostgresIndicatorService Routing
```python
# Route to appropriate stored procedure based on timeframe
if timeframe == 'weekly':
    result = await conn.fetchrow(
        "SELECT * FROM calculate_weekly_[indicator]_for_symbol($1)",
        symbol
    )
elif timeframe == 'monthly':
    result = await conn.fetchrow(
        "SELECT * FROM calculate_monthly_[indicator]_for_symbol($1)",
        symbol
    )
```

### Expected Results
- **First calculation**: Updates N rows (actual calculations)
- **Subsequent calculations**: Updates 0 rows (skips existing indicators)

## Testing Validation

### 1. Dynamic Window Verification
```python
# Get multiple days from same period
same_period_records = await conn.fetch("""
    SELECT datetime, close, indicators->'[indicator]' as indicator_value
    FROM daily_candles 
    WHERE symbol = $1 AND [period]_candle_key_id = $2
    ORDER BY datetime
""", symbol, period_key)

# Verify each day has different indicator value
indicator_values = [float(r['indicator_value']) for r in same_period_records]
unique_values = set(indicator_values)

assert len(unique_values) > 1, "Dynamic sliding window not working - all days have same value"
```

### 2. Recalculation Prevention Test
```python
# First call - should update rows
result1 = await calculate_indicator(symbol, timeframe)
assert result1['updated_rows'] > 0

# Second call - should update 0 rows  
result2 = await calculate_indicator(symbol, timeframe)
assert result2['updated_rows'] == 0
```

## Performance Considerations

### 1. Batch Processing
Process symbols individually to avoid memory issues:
```sql
FOR symbol_rec IN symbol_cursor LOOP
    -- Process one symbol at a time
END LOOP;
```

### 2. Index Requirements
Ensure indexes on:
- `daily_candles(symbol, [period]_candle_key_id)`
- `[period]_candles(symbol, [period]_sequence_number)`

### 3. Transaction Management
- Use single transaction per symbol
- Get diagnostics for row count tracking

## Common Mistakes to Avoid

### 1. ❌ Using Period Aggregated Values
```sql
-- WRONG: Uses weekly candle's close (same for all days in week)
wc_current.close as current_close
```

### 2. ✅ Using Daily Individual Values
```sql
-- CORRECT: Uses each day's individual close
dc.close as current_day_close
```

### 3. ❌ String-based Key Matching
```sql
-- WRONG: Fragile string manipulation
ON wc_prev.weekly_candle_key_id = (dc.symbol || '_W' || (wc_current.week_sequence_number - 1)::TEXT)
```

### 4. ✅ Sequence-based Matching
```sql
-- CORRECT: Reliable sequence number matching
ON wc_prev.symbol = dc.symbol AND wc_prev.week_sequence_number = (wc_current.week_sequence_number - 1)
```

## Future Indicator Implementation Checklist

When implementing any new indicator using this pattern:

- [ ] Identify reference period (previous week/month/quarter)
- [ ] Use individual daily values, not aggregated period values
- [ ] Implement sequence-based period matching
- [ ] Handle NULL reference periods (skip first periods)
- [ ] Add recalculation prevention logic
- [ ] Test dynamic sliding window behavior
- [ ] Verify 0 rows updated on subsequent calls
- [ ] Add proper error handling and logging
- [ ] Follow consistent JSONB storage format
- [ ] Include database index recommendations

## Conclusion

The Dynamic Sliding Window approach provides:
- **Mathematical Accuracy**: Each day gets its own calculation
- **Performance Efficiency**: Calculations done once, reused thereafter  
- **Consistent Pattern**: Same logic applies to all timeframe-based indicators
- **Scalability**: Works across any number of symbols and time periods

This pattern should be used for ALL future indicators that compare current values to previous periods, ensuring consistency and correctness across the entire system.