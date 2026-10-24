@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install-office.bat first.
  pause
  exit /b 1
)
echo Updating from the verified GitHub main release...
.venv\Scripts\python.exe scripts\update_office.py
if errorlevel 1 (
  pause
  exit /b 1
)
call start-office.bat
