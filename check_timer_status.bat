@echo off
echo ==========================================
echo 🕒 LATEST CANDLE TIMER STATUS
echo ==========================================

REM Check if server is running
curl -s -o nul -w "%%{http_code}" "http://127.0.0.1:8001/health" > temp_response.txt 2>nul
set /p response=<temp_response.txt
del temp_response.txt 2>nul

if not "%response%"=="200" (
    echo ❌ Server is not running
    pause
    exit /b 1
)

echo 📊 Current Status:
curl -s "http://127.0.0.1:8001/api/periodic-updates-status"

echo.
echo.
echo ==========================================
echo 💡 AVAILABLE COMMANDS:
echo ==========================================
echo 🚀 Start: POST http://127.0.0.1:8001/api/start-periodic-updates
echo 🛑 Stop:  POST http://127.0.0.1:8001/api/stop-periodic-updates  
echo 📊 Status: GET http://127.0.0.1:8001/api/periodic-updates-status
echo 🔄 Manual Update: POST http://127.0.0.1:8001/api/update-latest-candles
echo ==========================================

pause