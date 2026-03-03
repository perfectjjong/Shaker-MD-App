@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo   자동 시작 설정 (관리자 권한 불필요)
echo ========================================
echo.

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

echo [1/1] 시작 프로그램 폴더에 바로가기 생성 중...

:: 사용자 시작 프로그램 폴더에 바로가기 생성 (관리자 권한 불필요)
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudeCodeApprover.lnk'); $s.TargetPath = '%APP_DIR%\start-hidden.vbs'; $s.WorkingDirectory = '%APP_DIR%'; $s.Description = 'Claude Code Approver 자동 시작'; $s.Save()"

if %errorlevel% equ 0 (
    echo [완료] 자동 시작 등록 성공!
) else (
    echo [오류] 바로가기 생성 실패.
    pause
    exit /b 1
)

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
