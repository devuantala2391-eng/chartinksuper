@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo ==========================================
echo 🔥 CHARTINKSUPER SERVER STARTUP
echo ==========================================
echo 🧹 Cleaning up existing Python processes...

REM Kill all existing Python processes
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.exe >nul 2>&1
taskkill /F /IM python3.12.exe >nul 2>&1

REM Wait a moment for cleanup
timeout /t 2 /nobreak >nul

REM Find and kill process using port 8001
echo 🔍 Checking port 8001...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr :8001 ^| findstr LISTENING') do (
    echo ⚠️  Port 8001 is in use by process %%a, terminating...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM Double check if port is free
netstat -ano | findstr :8001 | findstr LISTENING >nul 2>&1
if %errorlevel% equ 0 (
    echo ❌ ERROR: Could not free port 8001
    echo Please manually close the application using port 8001
    pause
    exit /b 1
) else (
    echo ✅ Port 8001 is now available
)

echo 🚀 Starting ChartinkSuper FastAPI Server...
echo 🌐 Server URL: http://127.0.0.1:8001
echo 📚 API Docs: http://127.0.0.1:8001/docs
echo 🔄 RefreshDB: POST http://127.0.0.1:8001/refreshdb
echo 📡 SSE Stream: GET http://127.0.0.1:8001/refreshdb-progress-stream
echo ==========================================
echo 🎯 Press Ctrl+C to stop the server
echo 🔥 AUTO-RELOAD: Server will restart when you modify Python files
echo ==========================================

REM Check if main.py exists
if not exist python-api\main.py (
    echo ❌ ERROR: main.py not found in python-api directory
    echo Current directory: %CD%
    pause
    exit /b 1
)

REM Check if uvicorn is available
echo 🔍 Checking for uvicorn...
python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ uvicorn is not installed
    echo 📦 Installing uvicorn with [standard] extras...
    pip install "uvicorn[standard]"
    python -c "import uvicorn" >nul 2>&1
    if %errorlevel% neq 0 (
        echo ❌ Failed to install uvicorn, falling back to direct Python execution
        echo 💡 You can manually install uvicorn later with: pip install "uvicorn[standard]"
        cd python-api
        python -u main.py
        goto :end
    ) else (
        echo ✅ uvicorn installed successfully
    )
) else (
    echo ✅ uvicorn is available
)

REM Change to python-api directory and start the server with uvicorn
cd python-api
echo 🔄 Starting with auto-reload enabled...
echo 💡 The server will automatically restart when you modify Python files
echo 🔧 Using uvicorn with --reload flag for development
echo 🕒 Latest Candle Timer will appear in logs every 30 seconds
echo 💡 To start periodic updates: POST http://127.0.0.1:8001/api/start-periodic-updates
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload --log-level info

:end

REM If we get here, the server stopped
echo.
echo ==========================================
echo 🛑 Server stopped
echo ==========================================
pause