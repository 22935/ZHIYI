@echo off
REM ==========================================================================
REM  Kinlin_AI native runtime - one-click launcher (Windows)
REM  Starts / stops / inspects the full local stack via persistent_runtime.py.
REM
REM  RULE 1: Do NOT run as Administrator. The runtime refuses elevated tokens.
REM          Just double-click this file, or run it from a normal terminal.
REM  RULE 2: Keep this .bat at the project root (same folder as the 'apps' dir).
REM
REM  Usage:
REM    start-native.bat            -> start everything, including the desktop
REM    start-native.bat nogui      -> start without the Electron desktop
REM    start-native.bat status     -> show service status (read-only)
REM    start-native.bat stop       -> stop everything
REM    start-native.bat restart    -> stop, then start (with desktop)
REM    start-native.bat open       -> reopen the desktop window only
REM    start-native.bat menu       -> interactive choice menu
REM ==========================================================================

setlocal EnableDelayedExpansion

REM --- locate the managed venv python, home dir, and the real runtime script ---
set "PY=%LOCALAPPDATA%\ZhiyiNative\python\Scripts\python.exe"
set "HOME_DIR=%LOCALAPPDATA%\ZhiyiNative\default"
set "RT=%~dp0ops\scripts\infra\windows\native\persistent_runtime.py"

REM --- refuse to run elevated (the runtime itself rejects admin processes) ---
net session >nul 2>&1
if %errorlevel% == 0 (
    echo [ERROR] Do NOT run this as Administrator.
    echo         Right-click and choose "Open", or launch it from a normal terminal.
    echo         (The native runtime refuses elevated / high-integrity processes.)
    pause
    exit /b 1
)

REM --- pre-flight: make sure the pieces exist ---
if not exist "%PY%" (
    echo [ERROR] Managed python not found: %PY%
    echo         Run the project's dependency setup first.
    pause
    exit /b 1
)
if not exist "%RT%" (
    echo [ERROR] persistent_runtime.py not found: %RT%
    echo         This .bat must live at the project root (next to the 'apps' folder).
    pause
    exit /b 1
)

REM --- resolve the requested action (default: start with desktop) ---
set "ACTION=up"
set "DESKTOP=--desktop"
set "ARG=%~1"

if /i "%ARG%"=="status"  ( set "ACTION=status"  & set "DESKTOP=" )
if /i "%ARG%"=="stop"    ( set "ACTION=down"    & set "DESKTOP=" )
if /i "%ARG%"=="down"    ( set "ACTION=down"    & set "DESKTOP=" )
if /i "%ARG%"=="nogui"   ( set "ACTION=up"      & set "DESKTOP=" )
if /i "%ARG%"=="open"    ( set "ACTION=open"    & set "DESKTOP=" )
if /i "%ARG%"=="restart" ( set "ACTION=up"      & set "DESKTOP=--desktop" )
if /i "%ARG%"=="menu"    goto :MENU

REM --- restart: stop first, then fall through to the up below ---
if /i "%ARG%"=="restart" (
    echo [*] Stopping the stack first...
    "%PY%" "%RT%" down --home "%HOME_DIR%"
    echo.
)

echo [*] Action : %ACTION%
echo [*] Home   : %HOME_DIR%
echo [*] Logs   : %HOME_DIR%\logs
echo.
"%PY%" "%RT%" %ACTION% --home "%HOME_DIR%" %DESKTOP%
set "RC=%errorlevel%"
echo.
if %RC% == 0 (
    echo [OK] Command finished. Any started services keep running on their own.
) else (
    echo [FAIL] Command exited with code %RC%. Read the messages above.
)
echo      Log folder: %HOME_DIR%\logs
pause
exit /b %RC%

:MENU
echo.
echo  Select an action:
echo    1) Start (with desktop)
echo    2) Start (no desktop)
echo    3) Status
echo    4) Stop
echo    5) Restart
echo    6) Open desktop window only
set /p CHOICE=Enter 1-6: 
if "%CHOICE%"=="1" ( set "ACTION=up"   & set "DESKTOP=--desktop" )
if "%CHOICE%"=="2" ( set "ACTION=up"   & set "DESKTOP=" )
if "%CHOICE%"=="3" ( set "ACTION=status" & set "DESKTOP=" )
if "%CHOICE%"=="4" ( set "ACTION=down" & set "DESKTOP=" )
if "%CHOICE%"=="5" ( set "ACTION=up"   & set "DESKTOP=--desktop" )
if "%CHOICE%"=="6" ( set "ACTION=open" & set "DESKTOP=" )
echo.
"%PY%" "%RT%" %ACTION% --home "%HOME_DIR%" %DESKTOP%
set "RC=%errorlevel%"
echo.
if %RC% == 0 ( echo [OK] Done. ) else ( echo [FAIL] Exited with code %RC%. )
pause
exit /b %RC%
