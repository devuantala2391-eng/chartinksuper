# Candle Count Configuration

## Overview
The number of candles (historical data points) fetched from ChartInk API is now configurable through an environment variable.

## Configuration

### Using .env File (Recommended)
Edit the `python-api/.env` file and set the `DEFAULT_CANDLE_COUNT` variable:

```env
# Default candle count for ChartInk data fetching (default: 2000)
DEFAULT_CANDLE_COUNT=2000
```

### Available Options
- **DEFAULT_CANDLE_COUNT**: Number of historical candles to fetch
  - Default: 2000
  - Recommended range: 500-5000
  - Higher values = more historical data but slower fetching

## When to Adjust

### Increase candle count (e.g., 3000-5000) when:
- You need more historical data for long-term indicators
- Calculating indicators with large periods (e.g., 200-day moving average)
- Weekly/monthly SuperTrend with large periods (e.g., 30+ weeks)

### Decrease candle count (e.g., 500-1000) when:
- You only need recent data
- Faster data fetching is priority
- Working with shorter timeframe indicators

## Example Usage

1. For more accurate weekly SuperTrend (30,1.6):
```env
DEFAULT_CANDLE_COUNT=3000
```

2. For quick daily analysis:
```env
DEFAULT_CANDLE_COUNT=500
```

3. For comprehensive historical analysis:
```env
DEFAULT_CANDLE_COUNT=5000
```

## Note
After changing the value in .env file, restart the FastAPI server for changes to take effect.