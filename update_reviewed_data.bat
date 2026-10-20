@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run start_windows.bat once to install dependencies, then stop that server.
  pause
  exit /b 1
)
echo Close the running UniSched server before applying this data update.
echo Only the reviewed teacher assignments and missing new faculty will be updated.
pause
".venv\Scripts\python.exe" update_reviewed_data.py
if errorlevel 1 (
  echo Update failed. Review the message above.
  pause
  exit /b 1
)
pause
