# Weekly Indicators Implementation Reference

## Overview
This document contains the exact implementation details for weekly indicators calculated on a daily basis. Each day's weekly indicator value uses the current day's data combined with historical weekly data.

## Core Concept
- **Daily SMA(20)**: Uses 20 daily candles - first 19 candles show null, values start from candle 20
- **Weekly SMA(20)**: Uses 20 weekly candles - approximately first 90-100 daily candles show null (need 20 weeks of data)
- **Key Principle**: For any given day, weekly indicator = f(current day's close, previous 19 weeks' last trading day closes)

## Implementation Details

### 1. Weekly Volume
**Location**: `services/timeframeAggregator.js` (lines 179-203)

**Logic**:
- Cumulative volume from Monday to current day within the same week
- Resets every Monday
- For each day, sum all volumes from Monday up to and including current day

**Code Structure**:
```javascript
// Calculate cumulative weekly volume from Monday to current day
let cumulativeWeeklyVolume = 0;
const currentWeekNumber = getISOWeek(date);
const currentYear = date.getUTCFullYear();

// Go backwards from current candle to find all candles in the same week
for (let i = index; i >= 0; i--) {
  const candleDate = new Date(Number(dailyCandles[i].date));
  const candleWeek = getISOWeek(candleDate);
  const candleYear = candleDate.getUTCFullYear();
  
  if (candleYear !== currentYear || candleWeek !== currentWeekNumber) {
    break;
  }
  
  const volume = sanitizeNumericValue(dailyCandles[i].volume);
  if (volume !== null) {
    cumulativeWeeklyVolume += volume;
  }
}
```

### 2. Weekly SMA (Simple Moving Average)
**Location**: `services/weeklyIndicatorCalculator.js` (lines 31-104)

**Logic**:
1. Group all candles by calendar week (Monday-Friday)
2. For each day, collect 20 values:
   - Current day's close (weight: 1/20)
   - Previous 19 weeks' last trading day closes (usually Friday)
3. Calculate average of these 20 values

**Key Implementation Points**:
- Uses Monday as week start (getMonday helper function)
- Week key format: "YYYY-MM-DD" (Monday's date)
- Sorts weeks in descending order (most recent first)
- Filters candles to ensure we only use data before current index
- Returns null if less than 20 weeks of data available

**Validation Values** (for AAATECH.json):
- Last Friday (index 651): 80.52
- Last Wednesday (index 654): 81.11
- First non-null value: index 90

**Critical Code**:
```javascript
// Helper to get Monday of a week
function getMonday(d) {
  d = new Date(d);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.setDate(diff));
}

// Collect values: current day + last trading day of previous 19 weeks
const values = [];
values.push(sanitizeNumericValue(candle.close)); // Current day

// Previous weeks (going back in time)
for (let i = 1; i < period && targetWeekIndex + i < sortedWeeks.length; i++) {
  const weekKey = sortedWeeks[targetWeekIndex + i];
  const weekCandles = weeklyData.get(weekKey);
  
  if (weekCandles && weekCandles.length > 0) {
    const validCandles = weekCandles.filter(c => c.index < index);
    if (validCandles.length > 0) {
      const lastCandle = validCandles[validCandles.length - 1];
      values.push(sanitizeNumericValue(lastCandle.close));
    }
  }
}
```

### 3. Weekly EMA (Exponential Moving Average)
**Location**: `services/weeklyIndicatorCalculator.js` (lines 106-188)

**Logic**:
1. Calculate historical weekly EMA using Friday closes
2. For current day: EMA = (Current Close - Previous Week EMA) × Multiplier + Previous Week EMA
3. Multiplier = 2 / (period + 1)

**Status**: Implemented but needs verification of expected values

## Integration Point
**Location**: `services/timeframeAggregator.js` (lines 151-168)

The weekly indicators are calculated in the `mapAggregatedIndicators` function:
```javascript
// Calculate weekly indicators using the new daily-based calculation
const weeklyIndicatorValues = {};

indicators.forEach(indicator => {
  const { name, period, params } = indicator;
  
  switch (name.toLowerCase()) {
    case 'sma':
      weeklyIndicatorValues[`weekly_sma_${period}`] = calculateWeeklySMADaily(dailyCandles, period);
      break;
    case 'ema':
      weeklyIndicatorValues[`weekly_ema_${period}`] = calculateWeeklyEMADaily(dailyCandles, period);
      break;
    case 'rsi':
      weeklyIndicatorValues[`weekly_rsi_${period}`] = calculateWeeklyRSIDaily(dailyCandles, period || 14);
      break;
  }
});
```

## Testing Approach
To verify weekly SMA implementation:

1. Check null values:
   - Daily SMA(20): First value at index 19
   - Weekly SMA(20): First value at index 90 (approximately)

2. Verify calculation for any day:
   - Current day's close
   - Plus 19 previous Friday closes (or last trading day of week)
   - Average these 20 values

3. Test data points:
   - Use AAATECH.json
   - Check index 651 (Friday) = 80.52
   - Check index 654 (Wednesday) = 81.11

## Common Issues
1. **Week Grouping**: Must use Monday as week start, not ISO week numbers
2. **Index Filtering**: Must filter weekCandles to only include candles before current index
3. **Null Handling**: Need exactly 20 values for valid SMA, otherwise return null
4. **Date Objects**: Always create new Date objects to avoid mutation

## Future Indicators to Implement
- [ ] Weekly RSI
- [ ] Weekly Bollinger Bands
- [ ] Weekly MACD
- [ ] Weekly Stochastic
- [ ] Weekly SuperTrend

Each should follow the same pattern: current day's data + previous weeks' end-of-week data.