# PDF Automation (Unlock + OCR) — v6.1

A Windows-friendly tool that unlocks restricted PDFs, runs OCR with size‑aware compression, and adds page numbers. It supports both batch processing and a right-click Explorer action.

## What it does
- Detects print or copy‑restricted PDFs and **unlocks** them using Ghostscript.
- Runs **OCR** with OCRmyPDF (always re-OCRs each page to guarantee a clean text layer).
- Adds **page numbers** in "Page X of Y" format to the bottom of each page.
- Uses PDF/A-2 output with balanced compression to keep sizes reasonable.
- Supports two modes:
  - **Right‑click mode** (Explorer): Processes selected PDFs **in place**, creates a new `*_OCR.pdf` file, and moves the original into an `Originals\` subfolder. This is the primary intended use.
  - **Batch mode** (manual): Running the script without arguments scans the root folder, writes results to `_complete\`, and moves originals to `_processed\` (with timestamp/UUID to avoid collisions).

## Requirements
- Windows 10 or 11
- Python 3.x
- **Ghostscript**: Must be installed and accessible via the system's PATH.
- **Tesseract OCR**: Must be installed as it is a dependency for OCRmyPDF.
- Python packages as defined in `requirements.txt`.
- Use the project virtual environment (`C:\Utils\pdfconvert\venv`) when running the script.

Install required Python packages:
```bat
pip install -r requirements.txt
```

## Setup & Usage (Right-Click Method)

This is the recommended way to use the tool.

1.  **Install Dependencies**: Make sure Ghostscript and Tesseract are installed on your system.
2.  **Add Context Menu**: Navigate to the `registry` folder and double‑click `add_OCR_context_v6.1.reg`. You will need to approve the security prompt. This adds the "Convert to OCR (v6.1)" option to your right-click menu for PDF files.
3.  **Run**: In Explorer, select one or more PDFs, right-click, and choose **Convert to OCR (v6.1)**.
4.  **Results**: For each file processed, a new `*_OCR.pdf` file will be created in the same directory, and the original file will be moved into a new `Originals` subfolder.

## Core Files
- `pdf_automation_v6.1.py`: The main Python script containing all the logic.
- `run_single_pdf.bat`: A helper batch script that allows the context menu to reliably call the Python script with file paths that contain spaces.
- `registry/add_OCR_context_v6.1.reg`: The registry file for creating the right-click context menu item.
- `archives/`: Contains archived scripts and logs from previous versions.

## How it Works

### Unlock Check
The script opens the PDF with PyMuPDF and checks permissions for printing and copying. If restricted, it creates an unrestricted copy with Ghostscript:
```
gswin64c.exe -o unlocked.pdf -sDEVICE=pdfwrite -dPDFSETTINGS=/default input.pdf
```

### OCR with Compression
OCR is performed with OCRmyPDF using settings that preserve text quality and reduce size:
```
ocrmypdf.exe --skip-text --optimize 3 --jpeg-quality 40 --output-type pdf --deskew input.pdf output.pdf
```
- `--skip-text` OCRs only pages that do not already have text.
- `--optimize 3` and `--jpeg-quality 40` prioritize smaller output size.
- `--output-type pdf` writes standard searchable PDF output.

### Dependency Resolution
- The script now prefers `ocrmypdf.exe` from the **active Python environment** first (for example `venv\Scripts\ocrmypdf.exe`) before searching system PATH.
- This prevents global/user Python package conflicts from breaking OCR when the project venv is healthy.

### Page Numbering
After OCR, PyMuPDF is used to add "Page X of Y" to the bottom center of each page.

### Temp files and originals
- Intermediate files live in a temporary directory and are cleaned after each file.
- Originals are archived with a timestamp and short UUID suffix to prevent name collisions (`<name>_YYYYMMDD_HHMMSS_<id>.pdf`).

## Troubleshooting
- **Script fails silently**: The most common cause is a missing dependency. Ensure both Ghostscript and Tesseract are installed and their paths are correctly configured in your system's environment variables.
- **`SystemError` about `pydantic-core` incompatibility**:
  - Cause: A global/user `ocrmypdf` install is loading mismatched `pydantic` and `pydantic-core` versions.
  - Fix: Run using the project venv (the script now prefers this automatically), or repair global packages:
  ```bat
  python -m pip install --upgrade --force-reinstall "pydantic==2.12.5" "pydantic-core==2.41.5"
  ```
- **ChatGPT says "No text can be extracted"**: For a stubborn file, you can force re-OCR on every page with this manual command, though it may increase file size:
  ```bat
  ocrmypdf --force-ocr --output-type pdf "input.pdf" "fixed.pdf"
  ```
- **Want to tweak quality**: Adjust `--jpeg-quality` (e.g., 75 for smaller files or 95 for higher quality).
