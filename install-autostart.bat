@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo   자동 시작 설정
echo ========================================
echo.

:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [안내] 관리자 권한으로 다시 실행합니다...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 현재 디렉토리
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

:: Node.js 경로 확인
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Node.js가 설치되어 있지 않습니다.
    pause
    exit /b 1
)
for /f "delims=" %%i in ('where node') do set "NODE_PATH=%%i"

echo [1/2] Windows 서비스 등록 중...

:: 기존 작업 제거
schtasks /delete /tn "ClaudeCodeApprover" /f >nul 2>&1

:: 시작 시 자동 실행 예약 작업 등록
schtasks /create /tn "ClaudeCodeApprover" /tr "cmd /c cd /d \"%APP_DIR%\" && \"%NODE_PATH%\" src/server.js" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo [완료] 자동 시작 등록 성공!
) else (
    echo [오류] 등록 실패. 수동으로 시작 프로그램에 추가해주세요.
    pause
    exit /b 1
)

echo.
echo [2/2] 시작 프로그램 바로가기도 생성 중...

:: 시작 프로그램 폴더에 바로가기 생성 (백업용)
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudeCodeApprover.lnk'); $s.TargetPath = '%APP_DIR%\start-hidden.vbs'; $s.WorkingDirectory = '%APP_DIR%'; $s.Description = 'Claude Code Approver 자동 시작'; $s.Save()"

echo.
echo ========================================
echo   설정 완료!
echo ========================================
echo.
echo   PC 재부팅 시 서버가 자동 실행됩니다.
echo.
echo   제거하려면: remove-autostart.bat 실행
echo ========================================
pause
