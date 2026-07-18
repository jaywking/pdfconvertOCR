@echo off
setlocal

set "ROOT=%~dp0"
set "INSTALLED_PYTHON_EXE=%ROOT%python\python.exe"
set "SOURCE_PYTHON_EXE=C:\LocalVenvs\pdfconvertOCR\Scripts\python.exe"
set "MAIN_SCRIPT=pdf_automation_v6.2.py"

if exist "%ROOT%app_metadata.json" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$m = Get-Content -Raw '%ROOT%app_metadata.json' | ConvertFrom-Json; $m.mainScript"`) do set "MAIN_SCRIPT=%%I"
)

if exist "%ROOT%vendor\ghostscript\bin" set "PATH=%ROOT%vendor\ghostscript\bin;%PATH%"
if exist "%ROOT%vendor\tesseract" set "PATH=%ROOT%vendor\tesseract;%PATH%"
if exist "%ROOT%vendor\pngquant" set "PATH=%ROOT%vendor\pngquant;%PATH%"
if exist "%ROOT%vendor\tesseract\tessdata" set "TESSDATA_PREFIX=%ROOT%vendor\tesseract\tessdata"

if exist "%INSTALLED_PYTHON_EXE%" (
    set "PYTHON_EXE=%INSTALLED_PYTHON_EXE%"
) else (
    set "PYTHON_EXE=%SOURCE_PYTHON_EXE%"
)

echo Processing file: %1
if not exist "%PYTHON_EXE%" (
    if exist "%ROOT%setup_installed_app.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%setup_installed_app.ps1"
        if errorlevel 1 (
            echo Failed to prepare the installed PDFConvertOCR runtime.
            pause
            exit /b 1
        )
        set "PYTHON_EXE=%INSTALLED_PYTHON_EXE%"
    ) else (
        powershell -ExecutionPolicy Bypass -File "%ROOT%bootstrap.ps1"
        if errorlevel 1 (
            echo Failed to create the centralized virtual environment.
            pause
            exit /b 1
        )
        set "PYTHON_EXE=%SOURCE_PYTHON_EXE%"
    )
)

"%PYTHON_EXE%" "%ROOT%%MAIN_SCRIPT%" "%~1"
pause
