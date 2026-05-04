@echo off
setlocal

set "ROOT=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%install_right_click_context.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Right-click OCR menu setup completed.
) else (
    echo Right-click OCR menu setup failed with exit code %EXIT_CODE%.
)

pause
exit /b %EXIT_CODE%
