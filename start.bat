@echo off
chcp 65001 >nul 2>&1
title Claude Code Approver

echo ========================================
echo   Claude Code Mobile Approver
echo ========================================
echo.

:: Node.js 확인
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Node.js가 설치되어 있지 않습니다.
    echo https://nodejs.org 에서 설치해주세요.
    pause
    exit /b 1
)

:: 프로젝트 디렉토리로 이동
cd /d "%~dp0"

:: node_modules 확인
if not exist "node_modules" (
    echo [설치] npm 패키지 설치 중...
    npm install
    echo.
)

:: 서버 IP 표시
echo [정보] 모바일에서 아래 주소로 접속하세요:
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    call set IP=%%IP: =%%
    call echo   http://%%IP%%:3847
)
echo   http://localhost:3847
echo.
echo [정보] 종료하려면 Ctrl+C 를 누르세요.
echo ========================================
echo.

:: 서버 실행
node src/server.js
pause
