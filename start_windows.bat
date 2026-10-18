@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto check_python

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
    goto check_python
)
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv .venv
    if errorlevel 1 goto failed
    goto check_python
)
echo Python 3.11 or 3.12 is required. Install the 64-bit version from python.org.
echo Select "Add Python to PATH", then run this file again.
pause
exit /b 1

:check_python
.venv\Scripts\python.exe -c "import sys,struct; print('Using Python', sys.version); sys.exit(0 if sys.version_info[:2] in [(3,11),(3,12)] and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo This .venv uses an unsupported Python version or a 32-bit interpreter.
    echo Rename the .venv folder, install 64-bit Python 3.11 or 3.12, and try again.
    echo Keep the data folder: it contains your saved academic data.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto failed

echo.
echo Open http://127.0.0.1:8000 in your browser after the server starts.
echo Keep this window open. Press Ctrl+C to stop UniSched.
.venv\Scripts\python.exe run.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo UniSched could not start. Read the error above and share it for troubleshooting.
pause
exit /b 1
