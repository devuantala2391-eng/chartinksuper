@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo 🕒 STARTING PERIODIC CANDLE UPDATES
echo ==========================================
echo 🎯 This will start automatic updates every 2 minutes
echo 📊 Updates only run during market hours (9:15 AM - 3:30 PM)
echo ==========================================

REM Check if server is running
curl -s -o nul -w "%%{http_code}" "http://127.0.0.1:8001/health" > temp_response.txt 2>nul
set /p response=<temp_response.txt
del temp_response.txt 2>nul

if not "%response%"=="200" (
    echo ❌ ERROR: Server is not running on port 8001
    echo 💡 Please start the server first using run_server.bat
    echo.
    pause
    exit /b 1
)

echo ✅ Server is running, starting periodic updates...
echo.

REM Start periodic updates
curl -X POST "http://127.0.0.1:8001/api/start-periodic-updates?interval_minutes=2" -H "Content-Type: application/json" -d "{}"

echo.
echo ==========================================
echo ✅ PERIODIC UPDATES STARTED
echo ==========================================
echo 📊 Check the server terminal for timer updates
echo 🔍 Monitor at: http://127.0.0.1:8001/api/periodic-updates-status
echo 🛑 To stop: POST http://127.0.0.1:8001/api/stop-periodic-updates
echo ==========================================

pause