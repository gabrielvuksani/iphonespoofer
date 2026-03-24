@echo off
setlocal enabledelayedexpansion

set APP_NAME=iPhone Spoofer
set VERSION=1.0.0

echo ==================================================
echo   Building %APP_NAME% v%VERSION% for Windows
echo ==================================================
echo.

:: ── Find Python ──────────────────────────────────────
set "PYTHON="
for %%p in (python3 python py) do (
    where %%p >nul 2>&1 && (
        set "PYTHON=%%p"
        goto :found
    )
)
echo [!] Python 3 not found. Install from python.org
pause
exit /b 1
:found

:: ── Venv ─────────────────────────────────────────────
if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    %PYTHON% -m venv .venv
) else (
    echo [1/4] Using existing venv
)

set "VPYTHON=.venv\Scripts\python.exe"
set "VPIP=.venv\Scripts\pip.exe"

:: ── Dependencies ─────────────────────────────────────
echo [2/4] Installing dependencies...
%VPIP% install --no-cache-dir -q -r requirements.txt pyinstaller 2>nul
echo       Done

:: ── Clean ────────────────────────────────────────────
echo [3/4] Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul

:: ── Build ────────────────────────────────────────────
echo [4/4] Building executable...
echo       This takes 3-5 minutes...

%VPYTHON% -m PyInstaller ^
    --name "%APP_NAME%" ^
    --windowed ^
    --onedir ^
    --noconfirm ^
    --clean ^
    --log-level WARN ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --collect-all pymobiledevice3 ^
    --collect-all webview ^
    --hidden-import pymobiledevice3.cli.remote ^
    --hidden-import pymobiledevice3.remote.tunnel_service ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import webview.platforms.mshtml ^
    main_app.py

if exist "dist\%APP_NAME%" (
    echo.
    echo ==================================================
    echo   Build complete!
    echo ==================================================
    echo.
    echo   Output: dist\%APP_NAME%\
    echo   Run:    dist\%APP_NAME%\%APP_NAME%.exe
    echo.
) else (
    echo.
    echo [!] Build failed
)

pause
