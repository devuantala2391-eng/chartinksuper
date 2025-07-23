# ChartinkSuper - Stock Screener Application

## Project Structure

The project has been reorganized into three main directories for better organization and isolation:

```
chartinksuper/
├── frontend/           # Angular frontend application
├── node-api/          # Node.js API server
├── python-api/        # Python FastAPI server
└── README.md          # This file
```

### Frontend (Angular)
- **Path**: `frontend/`
- **Port**: 4200
- **Start Command**: 
  ```bash
  cd frontend
  npm install
  npm start
  ```

### Node.js API
- **Path**: `node-api/`
- **Port**: 8001
- **Database**: Local JSON files in `node-api/db/`
- **Features**: Stock data querying, indicator calculations, file uploads
- **Start Command**:
  ```bash
  cd node-api
  npm install
  node server.js
  ```

### Python API
- **Path**: `python-api/`
- **Port**: 8001 (shared with Node API for indicator calculations)
- **Database**: Local JSON files in `python-api/db/`
- **Features**: Technical indicator precalculation, real-time progress via SSE
- **Start Command**:
  ```bash
  cd python-api
  pip install -r requirements.txt
  python main.py
  ```

## Key Features

### Dynamic Indicator Parameters
- Volume: 0 parameters
- EMA/SMA: 1 parameter (period)
- SuperTrend: 2 parameters (period + multiplier)
- Bollinger Bands: 2 parameters (period + standard deviation)

### Technical Indicators Supported
- SuperTrend with ATR calculation
- SMA, EMA, RSI
- Bollinger Bands
- Weekly/Monthly OHLC aggregation
- Volume indicators

### Real-time Features
- Server-Sent Events (SSE) for progress tracking
- Multi-threaded indicator calculations
- Real-time progress updates in frontend

## API Isolation

Both APIs are completely isolated:
- Each has its own database copies
- Relative paths ensure no cross-dependencies
- Independent package.json and requirements.txt
- Separate configuration files

## Current Status
✅ All components working correctly
✅ Weekly SuperTrend (10,2) properly calculated
✅ SSE progress updates functional
✅ Multi-threading performance optimized
✅ Frontend dynamic parameters working