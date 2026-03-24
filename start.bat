@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo   iPhone Location Spoofer (Windows Dev Mode)
echo ==================================================
echo.

:: ── Find Python ──────────────────────────────────────
set "PYTHON="
for %%p in (python3 python py) do (
    where %%p >nul 2>&1 && (
        set "PYTHON=%%p"
        goto :found_python
    )
)
echo [!] Python 3 not found.
echo     Install from https://www.python.org/downloads/
echo     Make sure to check "Add Python to PATH" during install.
pause
exit /b 1

:found_python
for /f "tokens=*" %%v in ('%PYTHON% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%v
echo [+] Python %PY_VER% (%PYTHON%)

:: ── Venv ─────────────────────────────────────────────
if not exist ".venv" (
    echo [*] Creating virtual environment...
    %PYTHON% -m venv .venv
)

set "VPYTHON=.venv\Scripts\python.exe"
set "VPIP=.venv\Scripts\pip.exe"

:: ── Dependencies ─────────────────────────────────────
echo [*] Checking dependencies...
%VPIP% install --no-cache-dir -q -r requirements.txt 2>nul
echo [+] Dependencies ready

:: ── iTunes check ─────────────────────────────────────
where /q iTunes 2>nul
if errorlevel 1 (
    echo.
    echo [!] iTunes not found. iTunes is required on Windows for USB device communication.
    echo     Download from: https://www.apple.com/itunes/
    echo.
)

:: ── Free port ────────────────────────────────────────
netstat -ano | findstr :8080 >nul 2>&1
if not errorlevel 1 (
    echo [*] Port 8080 in use, attempting to free...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
    timeout /t 1 >nul
)

:: ── Tunnel ───────────────────────────────────────────
echo.
echo [*] Starting iOS tunnel...
echo     You may see a Windows admin prompt - click Yes.
echo.

:: Check if tunnel is already running
curl -s http://127.0.0.1:49151 >nul 2>&1
if not errorlevel 1 (
    echo [+] Tunnel already running
    goto :launch
)

:: Start tunneld - needs admin on Windows too
start /b "" %VPYTHON% -m pymobiledevice3 remote tunneld > %TEMP%\iphonespoofer-tunneld.log 2>&1

echo [*] Waiting for tunnel...
set STARTED=0
for /l %%i in (1,1,30) do (
    curl -s http://127.0.0.1:49151 >nul 2>&1
    if not errorlevel 1 (
        echo [+] Tunnel ready
        set STARTED=1
        goto :tunnel_done
    )
    timeout /t 1 >nul
)

:tunnel_done
if %STARTED%==0 (
    echo [!] Tunnel failed to start.
    echo     Checklist:
    echo       - iTunes installed
    echo       - iPhone connected via USB
    echo       - "Trust This Computer" accepted on iPhone
    echo       - Developer Mode enabled on iPhone
    type %TEMP%\iphonespoofer-tunneld.log 2>nul
    pause
    exit /b 1
)

:: ── Launch ───────────────────────────────────────────
:launch
echo.
echo [*] Starting web server...
echo.

:: Open browser after delay
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8080"

%VPYTHON% app.py
pause
