@echo off
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo ==========================================
echo 🔥 CHARTINKSUPER SERVER STARTUP
echo ==========================================
echo 🧹 Cleaning up existing Python processes...

REM Kill all existing Python processes
taskkill //F //IM python.exe >nul 2>&1
taskkill //F //IM python3.exe >nul 2>&1
taskkill //F //IM python3.12.exe >nul 2>&1

REM Wait a moment for cleanup
timeout /t 2 /nobreak >nul

REM Check if port 8001 is still in use
echo 🔍 Checking port 8001...
netstat -ano | findstr :8001 >nul
if %errorlevel% equ 0 (
    echo ⚠️  Port 8001 still in use, waiting for cleanup...
    timeout /t 3 /nobreak >nul
) else (
    echo ✅ Port 8001 is available
)

echo 🚀 Starting ChartinkSuper FastAPI Server...
echo 🌐 Server URL: http://127.0.0.1:8001
echo 📚 API Docs: http://127.0.0.1:8001/docs
echo 🔄 RefreshDB: POST http://127.0.0.1:8001/refreshdb
echo 📡 SSE Stream: GET http://127.0.0.1:8001/refreshdb-progress-stream
echo ==========================================
echo 🎯 Press Ctrl+C to stop the server
echo ==========================================

python -u simple_server.py