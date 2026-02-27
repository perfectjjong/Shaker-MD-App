@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo   자동 시작 제거
echo ========================================
echo.

:: 관리자 권한 확인
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [안내] 관리자 권한으로 다시 실행합니다...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 예약 작업 제거
schtasks /delete /tn "ClaudeCodeApprover" /f >nul 2>&1
echo [완료] 예약 작업 제거됨

:: 시작 프로그램 바로가기 제거
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudeCodeApprover.lnk" >nul 2>&1
echo [완료] 시작 프로그램 바로가기 제거됨

:: 실행 중인 서버 종료
taskkill /f /im node.exe /fi "WINDOWTITLE eq Claude Code Approver" >nul 2>&1

echo.
echo   자동 시작이 해제되었습니다.
echo.
pause
