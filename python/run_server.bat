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
echo ==========================================

REM Check if main.py exists
if not exist main.py (
    echo ❌ ERROR: main.py not found in current directory
    echo Current directory: %CD%
    pause
    exit /b 1
)

REM Start the server
python -u main.py

REM If we get here, the server stopped
echo.
echo ==========================================
echo 🛑 Server stopped
echo ==========================================
pause