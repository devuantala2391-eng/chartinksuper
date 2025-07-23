@echo off
echo Starting all services...

echo.
echo [1/4] Opening Visual Studio Code...
start "" code "D:\chartinksuper"

echo.
echo [2/4] Starting Angular project...
cd /d "D:\chartinksuper\stock-screener"
start cmd /k "npm start"

echo.
echo [3/4] Opening Task Manager...
start taskmgr

echo.
echo [4/4] Running server...
cd /d "D:\chartinksuper\python"
start cmd /k "run_server.bat"

echo.
echo [5/5] Opening Chrome with Angular project...
timeout /t 3 /nobreak > nul
start chrome "http://localhost:4200"

echo.
echo All services started successfully!
echo This window will close in 5 seconds...
timeout /t 5 /nobreak > nul
exit