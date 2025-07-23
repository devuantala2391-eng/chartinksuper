@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo 🚀 CHARTINKSUPER - STARTING ALL SERVICES
echo ==========================================

REM Check if all required directories exist
if not exist "frontend" (
    echo ❌ ERROR: frontend directory not found
    pause
    exit /b 1
)

if not exist "node-api" (
    echo ❌ ERROR: node-api directory not found
    pause
    exit /b 1
)

if not exist "python-api" (
    echo ❌ ERROR: python-api directory not found
    pause
    exit /b 1
)

echo 🔧 Starting services in sequence...
echo.

echo 📦 1/3 Installing Frontend Dependencies...
cd frontend
if not exist "node_modules" (
    echo Installing Angular dependencies...
    call npm install
)
cd ..

echo 📦 2/3 Installing Node API Dependencies...
cd node-api
if not exist "node_modules" (
    echo Installing Node.js API dependencies...
    call npm install
)
cd ..

echo 📦 3/3 Installing Python API Dependencies...
cd python-api
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt > nul 2>&1
cd ..

echo.
echo ==========================================
echo 🌟 ALL DEPENDENCIES INSTALLED
echo ==========================================
echo.
echo 🚀 Starting all services...
echo.
echo 📱 Frontend (Angular): http://localhost:4200
echo 🔧 Node API: http://localhost:8001
echo 🐍 Python API: http://localhost:8001
echo.
echo ⚠️  Note: Node and Python APIs share port 8001
echo    Only one should run at a time for calculations
echo.
echo Starting services in new windows...

REM Start Python API
start "Python API" cmd /k "cd python-api && python main.py"

REM Wait 3 seconds
timeout /t 3 /nobreak >nul

REM Start Node API
start "Node API" cmd /k "cd node-api && node server.js"

REM Wait 3 seconds
timeout /t 3 /nobreak >nul

REM Start Frontend
start "Angular Frontend" cmd /k "cd frontend && npm start"

echo.
echo ==========================================
echo ✅ ALL SERVICES STARTED
echo ==========================================
echo 🎯 Press any key to close this window
echo    (Services will continue running in separate windows)
echo ==========================================
pause