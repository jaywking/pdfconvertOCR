@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE=C:\LocalVenvs\pdfconvert\Scripts\python.exe"

echo Processing file: %1
if not exist "%PYTHON_EXE%" (
    powershell -ExecutionPolicy Bypass -File "%ROOT%bootstrap.ps1"
    if errorlevel 1 (
        echo Failed to create the centralized virtual environment.
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" "%ROOT%pdf_automation_v6.1.py" "%~1"
pause
