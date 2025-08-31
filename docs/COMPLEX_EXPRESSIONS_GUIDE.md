# Complex Expressions Guide

## New UI Features

### Expression Type Selector
Every condition now starts with an expression type selector that offers three options:
1. **Simple Field** - Traditional single indicator/field selection
2. **Arithmetic Expression** - Build expressions with +, -, ×, ÷
3. **Average Function** - Calculate average of multiple indicators

### Example: Daily Close + Daily Open > 5000

**UI Steps:**
1. Click the expression type dropdown (shows "Simple Field" by default)
2. Select "Arithmetic Expression"
3. You'll see:
   - An operator selector (default: +)
   - Two term fields
   - An "Add Term" button
4. Configure:
   - Term 1: Daily → Close
   - Operator: + (keep default)
   - Term 2: Daily → Open
5. Set comparison: > 5000

**Generated Query:** `(daily_close + daily_open) > 5000`

### Example: Average of RSI Across Timeframes

**UI Steps:**
1. Select "Average Function" from expression type
2. You'll see term fields without an operator
3. Configure terms:
   - Term 1: Daily → RSI(14)
   - Term 2: Weekly → RSI(14) [click "Add Term"]
   - Term 3: Monthly → RSI(14) [click "Add Term"]
4. Set comparison: > 50

**Generated Query:** `avg(daily_rsi_X, weekly_rsi_X, monthly_rsi_X) > 50`

### Visual UI Elements

- **Expression Type Selector**: Light blue background (#e8f4f8)
- **Arithmetic Operator**: Yellow background (#fff3cd) 
- **Expression Terms**: Light blue boxes (#f0f8ff) with:
  - Time period selector
  - Field/indicator selector
  - Parameter inputs for indicators
  - Red × button to remove (except when only 1 term)
- **Add Term Button**: Blue button that adds new terms

### Complex Expression on Right Side

The right side also supports complex expressions:
1. Select "Field" radio button
2. Similar expression builder appears
3. Can create expressions like: `avg(weekly_sma_X, monthly_sma_X) + 100`

### Supported Queries

Now you can create queries like:
- `(daily_close + daily_open) > 5000`
- `(daily_rsi_X + daily_rsi_Y) / 2 > 60`
- `daily_volume > (weekly_volume * 1.5)`
- `avg(daily_rsi_X, weekly_rsi_X, monthly_rsi_X) > 50`
- `daily_rsi_X > avg(daily_rsi_Y, weekly_rsi_X, monthly_rsi_Z) + 10`
- `(daily_sma_X - weekly_sma_X) > 100`

### Note
The backend fully processes all these complex expressions with proper:
- Timeframe aggregation (daily, weekly, monthly)
- Arithmetic operations
- Average calculations
- Nested expressions