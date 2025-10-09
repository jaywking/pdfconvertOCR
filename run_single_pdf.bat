@echo off
echo Processing file: %1
"C:\Utils\pdfconvert\venv\Scripts\python.exe" "C:\Utils\pdfconvert\pdf_automation_v6.1.py" "%~1"
pause