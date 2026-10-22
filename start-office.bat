@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install-office.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m office.web_server
pause
