@echo off
chcp 65001 >nul
REM ============================================================
REM Okinawa/nationwide relocation news collector - scheduled run
REM Intended to be run daily at 07:00 via Windows Task Scheduler.
REM ============================================================

cd /d "%~dp0"

if not exist "logs" mkdir "logs"

set PYTHONUTF8=1

echo ==== %date% %time% start ==== >> "logs\run.log"
"C:\Users\hyaen\AppData\Local\Python\pythoncore-3.14-64\python.exe" main.py >> "logs\run.log" 2>&1
echo ==== %date% %time% end (exit code: %ERRORLEVEL%) ==== >> "logs\run.log"

exit /b %ERRORLEVEL%
