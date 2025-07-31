@echo off
REM Completion notification hook for Windows
REM Makes noise when tasks are completed

echo.
echo ========================================
echo         TASK COMPLETED!
echo ========================================
echo.

REM Play Windows notification sounds
powershell -c "[console]::beep(523,200); [console]::beep(587,200); [console]::beep(659,200); [console]::beep(523,400)"

REM Also run the Python version if Python is available
python "%~dp0completion_hook.py" %* 2>nul

REM Show notification
msg "%username%" /TIME:5 "Task Completed! Check your terminal for results."

pause