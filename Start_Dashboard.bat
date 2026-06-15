@echo off
REM ============================================================
REM  Amazon.ae Seller Dashboard - one-click launcher (modular project)
REM  Double-click this file to start the app from app.py.
REM  First run: creates a local "venv" and installs requirements.txt.
REM  Every run after: just launches (fast).
REM ============================================================
setlocal
cd /d "%~dp0"

set "APP=app.py"

echo(
echo ===========================================
echo    Amazon.ae Seller Dashboard (modular)
echo ===========================================
powershell -NoProfile -Command "$d=(Get-ChildItem -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch 'venv|__pycache__' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1); if ($d) { Write-Host ('   Version 1.5  -  last updated ' + $d.LastWriteTime.ToString('yyyy-MM-dd HH:mm') + '  (newest: ' + $d.Name + ')') }"
echo(

REM --- locate Python -----------------------------------------
set "PY=python"
where python >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during install, then re-run this file.
  echo(
  pause
  exit /b 1
)

REM --- first-run setup ---------------------------------------
if not exist "venv\Scripts\activate.bat" (
  echo First run detected. Setting up the environment...
  echo This happens only once and may take a few minutes.
  echo(
  %PY% -m venv venv
  if errorlevel 1 ( echo [ERROR] Could not create venv. & pause & exit /b 1 )
  call "venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 ( echo [ERROR] Dependency install failed. & pause & exit /b 1 )
  echo(
  echo Setup complete.
  echo(
) else (
  call "venv\Scripts\activate.bat"
  REM ensure any newly-added dependencies are present (fast if already installed)
  python -m pip install -r requirements.txt -q 2>nul
)

REM --- stop any old dashboard server first (prevents stale code) ---
echo Stopping any old dashboard server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'streamlit' -and $_.CommandLine -match 'run' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

REM --- launch -------------------------------------------------
echo Starting the dashboard...
echo A browser tab will open at http://localhost:8501
echo Login:  admin  /  your local password
echo(
echo To STOP the app: close this window, or press Ctrl+C here.
echo(
python -m streamlit run "%APP%"

echo(
echo The dashboard has stopped.
pause
