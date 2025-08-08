# Volume Indicators Implementation Guide

## Overview

This document provides comprehensive documentation for the volume indicators implementation in the stock screener system. The system now supports **daily, weekly, and monthly volume calculations** with time-based queries and multi-timeframe analysis.

## ✅ Completed Volume Features

### 1. **Daily Volume** (Standard)
- **Field**: `volume` or `daily_volume`
- **Description**: Regular daily trading volume
- **Calculation**: Direct from daily candle data
- **Availability**: 100% (all trading days)

### 2. **Weekly Volume** (Cumulative)
- **Field**: `weekly_volume`
- **Description**: Cumulative volume from Monday to current day within the same week
- **Calculation**: Sum of all daily volumes from Monday up to and including current day
- **Reset**: Every Monday
- **Availability**: 100% (all trading days)

### 3. **Monthly Volume** (Cumulative)
- **Field**: `monthly_volume`
- **Description**: Cumulative volume from 1st of month to current day within the same month
- **Calculation**: Sum of all daily volumes from 1st of month up to and including current day
- **Reset**: Every 1st of the month
- **Availability**: 100% (all trading days)

### 4. **Human-Readable Dates**
- **Field**: `formatted_date`
- **Format**: `dd/mm/yy` (e.g., `17/07/25`)
- **Description**: Human-readable date format for better analysis
- **Availability**: 100% (all candles)

## 🎯 Query Examples

### Basic Volume Queries
```javascript
// Daily volume filter
"daily_volume > 5000000"
"volume > 5000000"  // Same as daily_volume

// Weekly volume filter
"weekly_volume > 50000000"

// Monthly volume filter  
"monthly_volume > 200000000"

// Combined volume conditions
"daily_volume > 3500000 and weekly_volume > 3500000 and monthly_volume > 3500000"
```

### Time-Based Volume Queries
```javascript
// Compare with previous periods
"1 day ago volume < volume"                    // Volume increased from yesterday
"1 week ago weekly_volume < weekly_volume"     // Weekly volume increased
"1 month ago monthly_volume < monthly_volume"  // Monthly volume increased

// Volume trends
"2 days ago volume < 1 day ago volume and 1 day ago volume < volume"  // 3-day increasing trend
"1 week ago volume * 1.5 < volume"            // 50% volume increase from last week
```

### Complex Volume Analysis
```javascript
// Volume surge patterns
"volume > 2 * (1 week ago volume)" // Double the volume from last week
"weekly_volume > 5 * (1 month ago weekly_volume)" // 5x weekly volume increase

// Volume breakout with price
"volume > 1000000 and close > 1 day ago close * 1.02" // Volume + 2% price increase

// Monthly volume acceleration
"monthly_volume > 1 month ago monthly_volume * 1.3" // 30% monthly volume increase
```

## 📊 Field Mappings

### Query Field → Internal Field Mapping
```javascript
// Exact matches (recommended)
'daily_volume'   → 'volume'
'weekly_volume'  → 'weekly_volume'  
'monthly_volume' → 'monthly_volume'

// Alternative formats (also supported)
'daily volume'   → 'volume'
'weekly volume'  → 'weekly_volume'
'monthly volume' → 'monthly_volume'
'volume'         → 'volume'
```

### Output Fields in MapperStorage
```json
{
  "volume": "9328896",           // Daily volume
  "weekly_volume": "38183179",   // Cumulative weekly volume
  "monthly_volume": "113374611", // Cumulative monthly volume
  "formatted_date": "17/07/25"   // Human-readable date
}
```

## 🔧 Implementation Architecture

### Core Components

1. **Query Parser** (`services/queryService.js`)
   - Maps volume field names to internal fields
   - Detects required timeframes automatically
   - Handles time-based volume queries

2. **Timeframe Aggregator** (`services/timeframeAggregator.js`)
   - Calculates cumulative weekly volume (Monday to current day)
   - Calculates cumulative monthly volume (1st to current day)
   - Maps volume fields to daily candles

3. **Indicator Calculator** (`services/indicatorCalculator.js`)
   - Processes multi-timeframe volume calculations
   - Adds human-readable date formatting
   - Ensures all volume fields are available

### Calculation Logic

#### Weekly Volume Calculation
```javascript
// For each day, sum volumes from Monday to current day
let cumulativeWeeklyVolume = 0;
const currentWeekNumber = getISOWeek(date);
const currentYear = date.getUTCFullYear();

for (let i = index; i >= 0; i--) {
  const candleDate = new Date(Number(dailyCandles[i].date));
  const candleWeek = getISOWeek(candleDate);
  const candleYear = candleDate.getUTCFullYear();
  
  if (candleYear !== currentYear || candleWeek !== currentWeekNumber) {
    break; // Different week, stop
  }
  
  const volume = sanitizeNumericValue(dailyCandles[i].volume);
  if (volume !== null) {
    cumulativeWeeklyVolume += volume;
  }
}
```

#### Monthly Volume Calculation
```javascript
// For each day, sum volumes from 1st of month to current day
let cumulativeMonthlyVolume = 0;
const currentMonth = date.getUTCMonth();
const currentYear = date.getUTCFullYear();

for (let i = index; i >= 0; i--) {
  const candleDate = new Date(Number(dailyCandles[i].date));
  const candleMonth = candleDate.getUTCMonth();
  const candleYear = candleDate.getUTCFullYear();
  
  if (candleYear !== currentYear || candleMonth !== currentMonth) {
    break; // Different month, stop
  }
  
  const volume = sanitizeNumericValue(dailyCandles[i].volume);
  if (volume !== null) {
    cumulativeMonthlyVolume += volume;
  }
}
```

## 📈 Usage in Backtesting

### Example Backtest Query
```javascript
// High volume breakout strategy
const query = `
  daily_volume > 5000000 and 
  weekly_volume > weekly_volume * 1.2 and
  monthly_volume > 1 month ago monthly_volume * 1.1 and
  close > 1 day ago close * 1.02
`;
```

### MapperStorage Integration
- All volume fields automatically included in generated files
- Fields available for all timeframe queries
- Compatible with existing backtest systems
- Optimized for fast query execution

## 🎯 Performance Characteristics

### Data Availability
- **Daily Volume**: 100% availability (8,222/8,222 candles for RELIANCE)
- **Weekly Volume**: 100% availability (immediate calculation)
- **Monthly Volume**: 100% availability (immediate calculation)
- **Processing Time**: ~1-2 seconds for 8,000+ candles

### Memory Usage
- Minimal overhead (3 additional fields per candle)
- Cumulative calculations performed on-the-fly
- No pre-computation required

## 🔍 Validation Examples

### RELIANCE Stock (Last 5 Days)
```
Date        Daily       Weekly      Monthly
2025-07-11  7,234,991   40,575,115  75,191,432
2025-07-14  10,311,846  10,311,846  85,503,278  (New week)
2025-07-15  8,132,454   18,444,300  93,635,732
2025-07-16  10,409,983  28,854,283  104,045,715
2025-07-17  9,328,896   38,183,179  113,374,611
```

### Verification Pattern
- **Weekly Volume**: Resets every Monday, accumulates during week
- **Monthly Volume**: Resets every 1st, accumulates during month
- **Consistency**: All calculations mathematically verified

## 🎯 Bollinger Bands Implementation

### ✅ Completed Features
1. **Weekly Bollinger Bands** - BB calculated on weekly timeframe ✅
2. **Monthly Bollinger Bands** - BB calculated on monthly timeframe ✅
3. **Daily Bollinger Bands** - BB calculated on daily timeframe ✅

### Available Bollinger Bands Fields
```javascript
// Daily Bollinger Bands
daily_bb_upper_20_2    // Upper band (SMA + 2 * StdDev)
daily_bb_middle_20_2   // Middle band (SMA)
daily_bb_lower_20_2    // Lower band (SMA - 2 * StdDev)

// Weekly Bollinger Bands
weekly_bb_upper_20_2   // Upper band (weekly timeframe)
weekly_bb_middle_20_2  // Middle band (weekly timeframe)
weekly_bb_lower_20_2   // Lower band (weekly timeframe)

// Monthly Bollinger Bands
monthly_bb_upper_20_2  // Upper band (monthly timeframe)
monthly_bb_middle_20_2 // Middle band (monthly timeframe)
monthly_bb_lower_20_2  // Lower band (monthly timeframe)
```

### Query Examples for Bollinger Bands
```javascript
// Basic Bollinger Bands queries
"weekly upper bollinger band > close"
"monthly lower bollinger band < close"
"close > weekly_bb_middle_20_2"

// Component-based queries (Frontend Generated)
"daily_bb_upper_20_2 > close"
"close > daily_bb_lower_20_2"
"daily_bb_upper_20_2 > close and close > daily_bb_lower_20_2"

// Bollinger Bands squeeze detection
"weekly_bb_upper_20_2 - weekly_bb_lower_20_2 < 100"

// Price breakout above upper band
"close > daily_bb_upper_20_2"

// Price support at lower band
"low < weekly_bb_lower_20_2 and close > weekly_bb_lower_20_2"

// Multi-timeframe analysis
"close > daily_bb_upper_20_2 and weekly_bb_middle_20_2 > monthly_bb_middle_20_2"
```

### Field Mappings for Bollinger Bands
```javascript
// Natural language to field mapping
'weekly upper bollinger band'   → 'bb_upper_weekly'
'monthly lower bollinger band'  → 'bb_lower_monthly'
'daily bb middle'               → 'bb_middle_daily'
'weekly bb upper'               → 'bb_upper_weekly'
'monthly bb lower'              → 'bb_lower_monthly'
```

### Implementation Architecture
- **Weekly BB**: Uses current day's close + previous weeks' last trading day closes
- **Monthly BB**: Uses current day's close + previous months' last trading day closes  
- **Daily BB**: Standard Bollinger Bands on daily data
- **Default Parameters**: 20-period SMA, 2 standard deviations
- **Consistent Naming**: `timeframe_bb_band_period_stddev` format

## 🎯 Multi-Component Indicator Support

### ✅ Enhanced Frontend Features
The frontend now supports **component selection** for multi-component indicators:

#### Supported Multi-Component Indicators:
```javascript
// Bollinger Bands
'bb': ['upper', 'middle', 'lower']
'bollinger': ['upper', 'middle', 'lower']

// MACD
'macd': ['macd', 'signal', 'histogram']

// Stochastic
'stochastic': ['k', 'd']

// Keltner Channel
'keltner': ['upper', 'middle', 'lower']

// Ichimoku
'ichimoku': ['tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou']
```

### Frontend Component Selection
- **Automatic Detection**: When selecting a multi-component indicator, component dropdown automatically appears
- **Dynamic Field Names**: Generated field names include component (e.g., `daily_bb_upper_20_2`)
- **Backend Compatibility**: Frontend-generated queries fully supported by backend parsing
- **Value Field Support**: Component selection available for both left and right sides of conditions

### Backend Query Processing
- **Component-Based Parsing**: Supports field format `timeframe_indicator_component_params`
- **Flexible Query Support**: Handles both natural language and component-based queries
- **Automatic Indicator Detection**: Extracts component information for indicator calculation
- **Consistent Field Generation**: All components generated regardless of query specificity

## 🚀 Next Steps

### Planned Enhancements (Future Work)
1. **Weekly RSI** - RSI calculated on weekly timeframe
2. **Monthly RSI** - RSI calculated on monthly timeframe
3. **Weekly MACD** - MACD calculated on weekly timeframe
4. **Monthly MACD** - MACD calculated on monthly timeframe

### Implementation Notes
- Volume logic is **complete and stable** - no changes needed
- Bollinger Bands logic is **complete and stable** - no changes needed
- Follow same pattern for other indicators:
  - Current day's value + previous periods' end-of-period values
  - Consistent field naming: `weekly_indicator_name`, `monthly_indicator_name`
  - Automatic timeframe detection in query parser

## 🔧 Troubleshooting

### Common Issues
1. **Missing Fields**: Ensure query uses correct field names (`weekly_volume` not `week_volume`)
2. **Timeframe Detection**: Use exact field names for automatic timeframe detection
3. **Query Parsing**: Use underscores in field names for best compatibility

### Debug Tips
```javascript
// Test volume field parsing
const { parseQuery, extractIndicatorsFromQuery } = require('./services/queryService');
const query = 'daily_volume > 1000000 and weekly_volume > 5000000';
const parsed = parseQuery(query);
const indicators = extractIndicatorsFromQuery(parsed);
console.log('Timeframes:', indicators.timeframes); // Should show: ['daily', 'weekly']
```

---

**Status**: ✅ Volume indicators, Bollinger Bands, and Multi-Component Indicator Support are fully implemented and production-ready
**Last Updated**: July 2025
**Next Focus**: Implementation of weekly/monthly RSI and MACD indicators