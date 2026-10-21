@echo off
setlocal
cd /d "%~dp0"
if not exist requirements.txt goto missing_project

rem Find a usable interpreter; the optional Windows py launcher is not required.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "OFFICE_PYTHON=python"
  goto found_python
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "OFFICE_PYTHON=py -3"
  goto found_python
)
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "OFFICE_PYTHON=python3"
  goto found_python
)
echo Python 3.10 or newer was not found.
echo Enable Python in PATH, then reopen this installer.
echo You do not need the optional py launcher.
pause
exit /b 1

:found_python
echo Using %OFFICE_PYTHON%
%OFFICE_PYTHON% -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Installation complete. Run start-office.bat.
pause
exit /b 0

:missing_project
echo Download and extract the complete project ZIP first.
echo Run this file from the same folder as requirements.txt.
pause
exit /b 1

:failed
echo Installation failed. Check the error above and try again.
pause
exit /b 1
