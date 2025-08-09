# Server Startup Guide

## Quick Start
To start the ChartinkSuper server, simply run:
```
run_server.bat
```

## Features of run_server.bat
The `run_server.bat` script provides a robust server startup with the following features:

### 🧹 Automatic Cleanup
- Terminates existing Python processes
- Frees up port 8001 if it's in use
- Ensures clean server startup

### 🔍 Dependency Management
- Checks for uvicorn installation
- Automatically installs uvicorn if missing
- Falls back to direct Python execution if needed

### 🔄 Development Features
- **Auto-reload**: Server automatically restarts when you modify Python files
- **Detailed logging**: Shows all server activities
- **Timer logs**: Latest candle timer appears every 30 seconds

### 🌐 Server Endpoints
Once started, the server provides:
- **Server URL**: http://127.0.0.1:8001
- **API Documentation**: http://127.0.0.1:8001/docs
- **Health Check**: http://127.0.0.1:8001/health
- **Refresh Database**: POST http://127.0.0.1:8001/refreshdb
- **Hard Refresh**: POST http://127.0.0.1:8001/api/hard-refresh
- **Start Scheduler**: POST http://127.0.0.1:8001/api/start-periodic-updates

## Stopping the Server
Press `Ctrl+C` in the terminal window to stop the server gracefully.

## Note
The deprecated `start_server.bat` has been removed in favor of the more robust `run_server.bat`.