# Dynamic Indicator Parameters Guide

## Overview

The stock screener now supports **dynamic indicator parameters**, allowing you to specify custom parameters for technical indicators in your queries. Instead of using hardcoded values, you can now request indicators with specific periods and configurations.

## Key Features

### 🔄 Dynamic Processing
- **Automatic cleanup**: mapperStorage is cleared and recreated for each query
- **On-demand calculation**: Indicators are calculated with user-specified parameters
- **Real-time processing**: No pre-computed data - everything is generated fresh

### 📊 Supported Indicators

| Indicator | Syntax | Default Parameters | Description |
|-----------|--------|-------------------|-------------|
| **RSI** | `rsi(period)` | `rsi(14)` | Relative Strength Index |
| **SMA** | `sma(period)` | `sma(20)` | Simple Moving Average |
| **EMA** | `ema(period)` | `ema(20)` | Exponential Moving Average |
| **Bollinger Bands** | `bb(period, stdDev)` | `bb(20, 2)` | Bollinger Bands |
| **SuperTrend** | `supertrend(period, multiplier)` | `supertrend(10, 3)` | SuperTrend |
| **MACD** | `macd(fast, slow, signal)` | `macd(12, 26, 9)` | MACD |
| **Stochastic** | `stochastic(k, d)` | `stochastic(14, 3)` | Stochastic Oscillator |
| **Williams %R** | `williamsr(period)` | `williamsr(14)` | Williams %R |

## Query Examples

### Basic Indicator Queries
```sql
-- Find stocks with RSI above 70
rsi(14) > 70

-- Find stocks below 20-period SMA
close < sma(20)

-- Find stocks with tight Bollinger Bands
bb(20, 1.5) - bb(20, 1.5) < 5

-- Find stocks above SuperTrend
close > supertrend(10, 3)
```

### Complex Queries
```sql
-- Oversold recovery pattern
1 day ago rsi(14) < 30 and rsi(14) > 50

-- Price breakout with momentum
close > sma(20) * 1.05 and rsi(14) < 70

-- Volume surge with RSI confirmation
volume > 1 week ago volume * 1.5 and rsi(14) > 60

-- Bollinger Band squeeze breakout
bb(20, 2) > close and close > sma(20)
```

### Time-Based Queries
```sql
-- RSI was oversold 3 days ago, now recovering
3 days ago rsi(14) < 30 and rsi(14) > 50

-- SMA crossover in the last week
1 week ago close < sma(50) and close > sma(50)

-- SuperTrend signal change
1 day ago supertrend(10, 3) > close and supertrend(10, 3) < close
```

## API Usage

### POST /query
```bash
curl -X POST http://localhost:3000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "rsi(14) > 70 and sma(20) < close"}'
```

### Response Format
```json
{
  "success": true,
  "query": "rsi(14) > 70 and sma(20) < close",
  "requiredIndicators": [
    {
      "name": "rsi",
      "period": 14,
      "params": {}
    },
    {
      "name": "sma", 
      "period": 20,
      "params": {}
    }
  ],
  "totalMatches": 45,
  "matches": [
    {
      "date": "1738630800000",
      "timestamp": "2025-01-14T19:00:00.000Z",
      "stock": "RELIANCE",
      "close": "1285.50",
      "day": "Tuesday"
    }
  ],
  "processedStocks": 1500
}
```

## Frontend Usage

### Web Interface (http://localhost:4200)

1. **Select Indicator**: Choose parameterized indicators like "RSI (with params)"
2. **Set Parameters**: Input boxes appear for each parameter
3. **Configure Values**: 
   - RSI: Period (default: 14)
   - SMA/EMA: Period (default: 20)
   - Bollinger Bands: Period, Std Dev (default: 20, 2)
   - SuperTrend: Period, Multiplier (default: 10, 3)
   - MACD: Fast, Slow, Signal (default: 12, 26, 9)
   - Stochastic: %K, %D (default: 14, 3)

### Preset Queries
- **📊 Volume Surge**: Volume analysis with momentum
- **📈 Price Breakout**: SMA(20) breakout with RSI filter
- **🔄 Trend Reversal**: SuperTrend(10,3) signals
- **💹 RSI Oversold**: RSI(14) below 30

## Implementation Details

### Processing Flow
1. **Parse Query**: Extract indicator parameters from query string
2. **Clean Storage**: Remove existing mapperStorage files
3. **Calculate Indicators**: Process all stocks with requested indicators
4. **Store Results**: Save processed data to mapperStorage
5. **Execute Query**: Run conditions against processed data
6. **Return Results**: Group matches by date

### File Structure
```
services/
├── indicatorCalculator.js     # Technical indicator calculations
├── queryService.js           # Enhanced query parsing
└── ...

mapperStorage/                # Generated for each query
├── STOCK1_piped.json         # Processed data with indicators
├── STOCK2_piped.json
└── ...
```

### Data Format
Each stock file contains candles with calculated indicators:
```json
{
  "data": [
    {
      "open": "1280.00",
      "high": "1295.50", 
      "low": "1275.00",
      "close": "1285.50",
      "volume": "1500000",
      "date": "1738630800000",
      "day": "Tuesday",
      "indicator_1": "65.34",
      "indicator_2": "1270.25",
      "indicator_3": "1300.50",
      "indicator_4": "1240.00",
      "indicator_5": "1250.00"
    }
  ]
}
```

## Performance Considerations

### Processing Time
- **First Query**: ~30-60 seconds (processes all stocks)
- **Indicator Complexity**: More complex indicators take longer
- **Stock Count**: ~1500 stocks processed per query

### Optimization Tips
1. **Specific Queries**: Use targeted conditions to reduce processing
2. **Standard Parameters**: Common parameters may be cached in future
3. **Batch Processing**: Multiple conditions in one query are more efficient

## Error Handling

### Common Errors
```json
{
  "error": "Invalid query format",
  "details": "No valid operator found in condition: rsi(14) 70",
  "hint": "Example: \"rsi(14) > 70 and sma(20) < close\""
}
```

### Troubleshooting
1. **Syntax**: Ensure proper operator spacing
2. **Parameters**: Check parameter count and types
3. **Database**: Verify stock data exists in `/db` folder
4. **Memory**: Large queries may require more system memory

## Migration from Legacy

### Old Format → New Format
```sql
-- Old (still supported)
daily rsi > 70

-- New (recommended)
rsi(14) > 70
```

### Backward Compatibility
- Legacy field names still work
- Gradual migration recommended
- Both formats can be mixed in queries

## Best Practices

1. **Parameter Selection**: Choose appropriate periods for your analysis
2. **Query Design**: Combine multiple indicators for robust signals
3. **Time Frames**: Use time-based queries for pattern analysis
4. **Performance**: Avoid overly complex queries on large datasets

---

**Note**: This feature processes indicators dynamically for each query, providing maximum flexibility but requiring processing time. The system automatically handles cleanup and recreation of processed data.