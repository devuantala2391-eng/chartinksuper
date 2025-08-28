# Monthly Key System Design

## Current State Analysis
Based on analysis of existing week_key system:

### Week_Key System (Current)
- `daily_candles.week_key` (1, 2, 3, ...) links to `weekly_candles.week_sequence_number` (1, 2, 3, ...)
- `daily_candles.weekly_candle_key_id` directly references `weekly_candles.weekly_candle_key_id`
- Week sequences start from 1 (mistake - should have been 0)

### Monthly System (Current Issues)
- No monthly_key in daily_candles or weekly_candles
- Month sequences start from 1 (same mistake as weekly)
- No direct relationship between daily/weekly and monthly candles

## Required Implementation

### 1. Database Schema Changes

#### Daily Candles Table
```sql
ALTER TABLE daily_candles 
ADD COLUMN monthly_key INTEGER,
ADD COLUMN monthly_candle_key_id VARCHAR(50);

CREATE INDEX idx_daily_monthly_key ON daily_candles(monthly_key);
CREATE INDEX idx_daily_monthly_key_id ON daily_candles(monthly_candle_key_id);
```

#### Weekly Candles Table  
```sql
ALTER TABLE weekly_candles 
ADD COLUMN monthly_key INTEGER,
ADD COLUMN monthly_candle_key_id VARCHAR(50);

CREATE INDEX idx_weekly_monthly_key ON weekly_candles(monthly_key);
CREATE INDEX idx_weekly_monthly_key_id ON weekly_candles(monthly_candle_key_id);
```

#### Monthly Candles Table (Fix sequence to start from 0)
```sql
-- Update existing data to start from 0
UPDATE monthly_candles SET month_sequence_number = month_sequence_number - 1;
```

### 2. Relationship Logic

#### Monthly Key Assignment
- monthly_key = 0 for first month (November 2024)
- monthly_key = 1 for second month (December 2024) 
- etc.

#### Mapping Logic
```
daily_candles.monthly_key ↔ monthly_candles.month_sequence_number
weekly_candles.monthly_key ↔ monthly_candles.month_sequence_number
daily_candles.monthly_candle_key_id ↔ monthly_candles.monthly_candle_key_id
```

### 3. Data Population Strategy

#### For Daily Candles
```python
for daily_candle in daily_candles:
    # Find which month this daily candle belongs to
    candle_date = daily_candle.datetime
    
    # Find matching monthly candle
    monthly_candle = find_monthly_candle_containing_date(candle_date)
    
    daily_candle.monthly_key = monthly_candle.month_sequence_number
    daily_candle.monthly_candle_key_id = monthly_candle.monthly_candle_key_id
```

#### For Weekly Candles  
```python
for weekly_candle in weekly_candles:
    # Find which month this weekly candle belongs to (use start date)
    week_start_date = weekly_candle.week_start_datetime
    
    # Find matching monthly candle
    monthly_candle = find_monthly_candle_containing_date(week_start_date)
    
    weekly_candle.monthly_key = monthly_candle.month_sequence_number  
    weekly_candle.monthly_candle_key_id = monthly_candle.monthly_candle_key_id
```

### 4. Foreign Key Considerations

#### Option A: Formal Foreign Keys
```sql
ALTER TABLE daily_candles 
ADD CONSTRAINT fk_daily_monthly 
FOREIGN KEY (monthly_candle_key_id) 
REFERENCES monthly_candles(monthly_candle_key_id);

ALTER TABLE weekly_candles 
ADD CONSTRAINT fk_weekly_monthly 
FOREIGN KEY (monthly_candle_key_id) 
REFERENCES monthly_candles(monthly_candle_key_id);
```

#### Option B: Soft References (Recommended)
- Keep relationships as soft references for flexibility
- Use indexes for performance
- Easier to maintain during development

### 5. Edge Cases to Handle

1. **Cross-Month Weeks**: A weekly candle that spans two months
   - **Solution**: Assign to the month where the week starts
   
2. **Month Boundaries**: Daily candles at month boundaries
   - **Solution**: Use daily candle date to determine month
   
3. **Data Consistency**: Ensuring all candles have proper monthly_key
   - **Solution**: Add validation checks
   
4. **Sequence Number Gaps**: If monthly data is missing
   - **Solution**: Use continuous sequence numbering based on chronological order

### 6. Implementation Steps

1. Add columns to daily_candles and weekly_candles tables
2. Fix monthly_candles sequence numbers (subtract 1 from all)
3. Populate monthly_key and monthly_candle_key_id for existing data
4. Update candle generation logic to assign monthly_key automatically
5. Add validation and testing
6. Create indexes and optimize performance

### 7. Testing Scenarios

1. **Basic Relationships**: Verify daily ↔ monthly and weekly ↔ monthly links
2. **Cross-Month Boundaries**: Test weeks/days that span month boundaries  
3. **Sequence Continuity**: Ensure no gaps in monthly_key assignments
4. **Performance**: Test query performance with new indexes
5. **Data Integrity**: Verify all candles have proper monthly relationships