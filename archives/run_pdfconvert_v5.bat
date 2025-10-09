@echo off
REM ------------------------------------------------------------
REM Batch launcher for pdf_automation_v5.py
REM • Double-click with NO args  → batch-scan C:\Utils\pdfconvert
REM • Drag-and-drop / pass file paths → forwards them to the script
REM • Works with the new multi-select right-click handler (%*)
REM ------------------------------------------------------------

:: Change to the folder this BAT lives in
pushd "%~dp0"

:: OPTIONAL: activate a virtual environment first
:: call "%~dp0venv\Scripts\activate.bat"

:: Run the Python script, forwarding any arguments (%*)
python "%~dp0pdf_automation_v5.py" %*

:: Return to original directory, keep window open for review
popd
echo.
pause
