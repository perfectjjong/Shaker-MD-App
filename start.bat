@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

title Claude Code Approver

echo ========================================
echo   Claude Code Mobile Approver
echo ========================================
echo.

REM --- Check Node.js ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    REM Try common Node.js install paths
    if exist "%ProgramFiles%\nodejs\node.exe" (
        set "PATH=%ProgramFiles%\nodejs;%PATH%"
    ) else if exist "%ProgramFiles(x86)%\nodejs\node.exe" (
        set "PATH=%ProgramFiles(x86)%\nodejs;%PATH%"
    ) else if exist "%APPDATA%\nvm\current\node.exe" (
        set "PATH=%APPDATA%\nvm\current;%PATH%"
    ) else if exist "%USERPROFILE%\.nvm\current\node.exe" (
        set "PATH=%USERPROFILE%\.nvm\current;%PATH%"
    ) else (
        echo [ERROR] Node.js not found!
        echo   Install from: https://nodejs.org
        echo.
        pause
        exit /b 1
    )
    echo [OK] Node.js found: added to PATH
)

for /f "tokens=*" %%v in ('node -v 2^>nul') do echo [OK] Node.js %%v

REM --- Move to project directory ---
cd /d "%~dp0"

REM --- Install npm packages if needed ---
if not exist "node_modules" (
    echo [SETUP] Installing npm packages...
    call npm install
    echo.
)

REM --- Show access URLs ---
echo.
echo [INFO] Access from mobile:
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    echo   http://!IP!:3847
)
echo   http://localhost:3847
echo.
echo [INFO] Press Ctrl+C to stop the server.
echo ========================================
echo.

REM --- Start server ---
node src/server.js
pause
