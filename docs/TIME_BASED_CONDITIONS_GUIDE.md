# Time-Based Conditions Guide

## Overview
The stock screener now supports time-based conditions, allowing you to compare current values with historical values from n days ago.

## How to Use

### In the Frontend (http://localhost:4200)

1. **Days Ago Field**: Each condition now has a "Days ago" input field
   - Leave empty or enter 0 for current value
   - Enter 1 for yesterday's value
   - Enter any positive number for that many days ago

2. **Example Conditions**:
   - Find stocks where volume increased from yesterday:
     - Days ago: 1, Field: Volume, Operator: Less than, Value: 100000
     - AND
     - Days ago: (empty), Field: Volume, Operator: Greater than, Value: 100000

   - Find stocks that recovered from oversold RSI in 3 days:
     - Days ago: 3, Field: Daily RSI, Operator: Less than, Value: 30
     - AND
     - Days ago: (empty), Field: Daily RSI, Operator: Greater than, Value: 50

### API Examples

```bash
# Volume increased from yesterday
curl -X POST http://localhost:3000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "1 day ago volume < 100000 and volume > 100000"}'

# RSI recovery in 3 days
curl -X POST http://localhost:3000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "3 days ago daily rsi < 30 and daily rsi > 50"}'

# Price gain of 10% in 5 days
curl -X POST http://localhost:3000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "5 days ago close < 100 and close > 110"}'

# Complex multi-day volume trend
curl -X POST http://localhost:3000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "2 days ago volume < 50000 and 1 day ago volume > 100000 and volume > 150000"}'
```

## Supported Fields
All indicators and price fields support time-based comparisons:
- Price fields: open, high, low, close, volume
- Daily indicators: daily rsi, daily sma, daily ema, daily supertrend, daily upper/lower bollinger band
- Weekly indicators: weekly rsi, weekly sma, weekly ema, weekly supertrend, weekly upper/lower bollinger band
- Percent changes: daily percent change, weekly percent change

## Query Syntax
The query parser recognizes patterns like:
- `n day ago <field>` (for n = 1)
- `n days ago <field>` (for n > 1)

Examples:
- `1 day ago volume`
- `5 days ago close`
- `10 days ago daily rsi`
- `3 days ago weekly sma`

## Implementation Details

### Backend (queryService.js)
- `parseField()`: Enhanced to recognize "n days ago" pattern using regex
- `getHistoricalFieldValue()`: New function to retrieve values from past candles
- `evaluateCondition()`: Updated to handle both current and historical field comparisons
- `getDataAvailabilityIndex()`: Considers maxDaysAgo when determining starting index

### Frontend (Angular)
- Added `daysAgo` property to Condition interface
- Added number input field for days ago in the UI
- Updated `buildQuery()` to prepend "n days ago" when daysAgo is specified
- Added help text to guide users on using the feature

## Testing
Run the test script to verify functionality:
```bash
node testTimeBasedQueries.js
```

This will test various time-based query scenarios and show the results.