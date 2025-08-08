# Latest Candle Update Service

## Overview

The Latest Candle Update Service is designed to efficiently update only today's latest candle data for all symbols every 2 minutes during market hours. This service ensures real-time data updates without the overhead of re-fetching complete historical data.

## Features

✅ **Resource Efficient**: Fetches only 1 candle (size=1) per symbol instead of full historical data  
✅ **Smart Updates**: Only updates files when candle data has actually changed  
✅ **Market Hours Aware**: Runs only during trading hours (9:15 AM - 3:30 PM IST, Mon-Fri)  
✅ **Concurrent Processing**: Uses async processing for maximum speed  
✅ **Non-Destructive**: Preserves all historical data, only updates/appends latest candle  
✅ **Comprehensive Logging**: Detailed logs with statistics and error handling  

## Implementation Details

### Core Components

1. **LatestCandleUpdater** (`services/latest_candle_updater.py`)
   - Main service class handling candle updates
   - Market hours detection
   - Concurrent symbol processing
   - Data comparison and smart updates

2. **API Endpoints** (integrated in `main.py`)
   - `/api/update-latest-candles` - Manual update trigger
   - `/api/start-periodic-updates` - Start 2-minute periodic updates
   - `/api/stop-periodic-updates` - Stop periodic updates
   - `/api/periodic-updates-status` - Check service status

3. **Standalone Service** (`services/latest_candle_service.py`)
   - Independent background service
   - Can run separately from main API server

### Data Flow

```
1. Check market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
2. For each symbol:
   - Fetch latest candle (size=1) from Chartink API
   - Load existing JSON file
   - Compare timestamps and OHLCV data
   - Update only if data changed or new day
   - Save updated file
3. Log statistics (updated/unchanged/errors)
4. Wait 2 minutes and repeat
```

## Usage

### Option 1: Via API Endpoints

Start the main server and use API endpoints:

```bash
# Start main server
python python-api/main.py

# Then use API endpoints:
curl -X POST "http://127.0.0.1:8001/api/start-periodic-updates"
curl -X GET "http://127.0.0.1:8001/api/periodic-updates-status"
curl -X POST "http://127.0.0.1:8001/api/stop-periodic-updates"
```

### Option 2: Standalone Service

Run the service independently:

```bash
cd python-api
python services/latest_candle_service.py
```

### Option 3: Manual Updates

Update latest candles on-demand:

```bash
curl -X POST "http://127.0.0.1:8001/api/update-latest-candles"
```

## Configuration

### Environment Variables

- `DEFAULT_SIZE`: Default candle count for historical data (not used for latest updates)

### Market Hours

- **Trading Days**: Monday to Friday
- **Trading Hours**: 9:15 AM to 3:30 PM IST
- **Behavior**: Service automatically skips updates outside market hours

### Update Frequency

- **Default**: Every 2 minutes
- **Customizable**: Can be changed via API parameter

## File Structure

```
python-api/
├── services/
│   ├── latest_candle_updater.py      # Core update logic
│   ├── latest_candle_service.py      # Standalone service
│   └── chartink_service.py           # Chartink API integration
├── main.py                           # FastAPI server with endpoints
└── latest_candle_updates.log         # Service logs
```

## JSON Data Structure

Each symbol's JSON file contains an array of candles:

```json
[
  {
    "high": 1407.8,
    "low": 1385.0,
    "open": 1392.3,
    "close": 1387.6,
    "volume": 7748361,
    "timestamp": 1753641000000
  }
]
```

The service updates only the last candle or appends a new one for the current day.

## Logging

### Log Levels

- **INFO**: Normal operations, market hours status, update statistics
- **ERROR**: API failures, file I/O errors, service errors

### Log Output

```
2025-01-27 14:30:15 - INFO - [LATEST_CANDLE] Starting latest candle update cycle
2025-01-27 14:32:47 - INFO - [LATEST_CANDLE] Update completed: 245 updated, 1823 unchanged, 12 errors
```

### Log Files

- Console output for real-time monitoring
- `latest_candle_updates.log` for persistent logging

## Performance

### Benchmarks

- **Speed**: Processes ~2000 symbols in 30-60 seconds
- **Efficiency**: Only fetches 1 candle per symbol (vs 200+ for full refresh)
- **Concurrency**: 50 concurrent requests with semaphore control
- **Resource Usage**: Minimal CPU and memory footprint

### Optimizations

- Client pool reuse for HTTP connections
- Async/await for non-blocking operations
- Smart data comparison to avoid unnecessary writes
- Market hours check to prevent useless API calls

## Error Handling

### Automatic Recovery

- Failed symbol updates don't stop the entire process
- Individual errors are logged but don't crash the service
- Client connection pool automatically recovers from network issues

### Error Types

- **API Errors**: Invalid symbols, network timeouts, rate limits
- **File Errors**: Permission issues, disk space, corrupted files
- **Data Errors**: Invalid timestamps, malformed responses

## Integration with Existing System

### Compatibility

- **Database**: Uses existing `db/` folder structure
- **Format**: Maintains existing JSON candle format
- **Indicators**: Latest candles are immediately available for indicator calculations
- **Frontend**: No changes needed - existing queries work seamlessly

### Coexistence

- Can run alongside full database refresh operations
- Does not interfere with existing API endpoints
- Independent service can run on separate schedule

## Monitoring

### Health Checks

```bash
# Check if service is running
curl -X GET "http://127.0.0.1:8001/api/periodic-updates-status"

# Response:
{
  "is_running": true,
  "is_market_hours": true
}
```

### Statistics

Each update cycle provides:
- Total symbols processed
- Successfully updated count
- Unchanged (no update needed) count
- Error count with details

## Troubleshooting

### Common Issues

1. **Service not updating during market hours**
   - Check system time zone
   - Verify market hours logic (9:15 AM - 3:30 PM IST)

2. **High error rates**
   - Check network connectivity
   - Verify Chartink API access
   - Review authentication cookies

3. **Files not updating**
   - Check file permissions in `db/` folder
   - Verify disk space availability
   - Review error logs for specific failures

### Debug Mode

Add debug logging by modifying the logging level:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

- [ ] Configurable market hours for different exchanges
- [ ] Websocket integration for real-time updates
- [ ] Database storage option (PostgreSQL/MongoDB)
- [ ] Metrics and monitoring dashboard
- [ ] Alert system for high error rates
- [ ] Symbol-specific update frequencies

## API Reference

### POST /api/update-latest-candles

Manually trigger latest candle updates.

**Request Body**: 
```json
{
  "symbols": ["RELIANCE", "TCS"] // Optional, defaults to all symbols
}
```

**Response**:
```json
{
  "success": true,
  "summary": {
    "total": 2,
    "updated": 1,
    "unchanged": 1,
    "errors": 0
  },
  "details": {
    "RELIANCE": "Updated successfully - 245 total candles",
    "TCS": "No update needed - data unchanged"
  }
}
```

### POST /api/start-periodic-updates

Start periodic updates every N minutes.

**Query Parameters**:
- `interval_minutes`: Update interval (default: 2)

**Response**:
```json
{
  "success": true,
  "message": "Periodic updates started (every 2 minutes)",
  "interval_minutes": 2
}
```

### POST /api/stop-periodic-updates

Stop periodic updates.

**Response**:
```json
{
  "success": true,
  "message": "Periodic updates stopped"
}
```

### GET /api/periodic-updates-status

Get current service status.

**Response**:
```json
{
  "is_running": true,
  "is_market_hours": true
}
```