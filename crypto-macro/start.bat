@echo off
rem Double-click to run Crypto Macro locally. Keep this window open while using the app.
cd /d "%~dp0"

set "PY=python"
where py >/dev/null 2>/dev/null && set "PY=py -3"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :failed
)
echo Installing requirements...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt || goto :failed
if not exist .env copy .env.example .env >nul

echo.
echo Starting on http://127.0.0.1:8000  (close this window to stop)
start "" cmd /c "timeout /t 4 >/dev/null & start http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000

:failed
echo.
echo Something went wrong - copy the messages above and send them to Claude.
pause
