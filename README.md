# PDF Automation (Unlock + OCR) — v6.1

A Windows-friendly tool that unlocks restricted PDFs, runs OCR with size-aware compression, adds page numbers, and preserves useful file sorting dates. It supports both batch processing and a right-click Explorer action.

## What it does
- Detects print or copy‑restricted PDFs and **unlocks** them using Ghostscript.
- Runs **OCR** with OCRmyPDF to create a searchable text layer.
- Adds **page numbers** in "Page X of Y" format to the bottom of each page.
- Preserves the original PDF's Modified Date on the generated `*_OCR.pdf` output.
- Uses standard searchable PDF output with balanced compression to keep sizes reasonable.
- Supports two modes:
  - **Right-click mode** (Explorer): Processes selected PDFs **in place**, creates a new `*_OCR.pdf` file with the source file's Modified Date, and moves the original into an `Originals\` subfolder. This is the primary intended use.
  - **Batch mode** (manual): Running the script without arguments scans the root folder, writes results to `_complete\`, and moves originals to `_processed\` (with timestamp/UUID to avoid collisions).

## Quick Install

For coworkers and non-technical users, use the packaged Windows installer from GitHub Releases:

1. Download `PDFConvertOCR-Setup-v6.1.1.exe`.
2. Double-click the installer.
3. Right-click a PDF and choose **Convert to OCR (v6.1)**.

The installer is designed to install per-user under `%LOCALAPPDATA%\PDFConvertOCR`, bundle the OCR runtime tools, and create the right-click menu automatically.

## How To Use It

PDFConvertOCR runs from Windows File Explorer. It does not open as a normal desktop app.

1. Open the folder that contains the PDF.
2. Right-click the PDF file.
3. Choose **Convert to OCR (v6.1)**.
4. Wait for the conversion window to finish.

The tool creates a searchable `*_OCR.pdf` next to the selected PDF, keeps the source file's Modified Date, and moves the original into an `Originals\` folder.

## Source Checkout Requirements
- Windows 10 or 11
- Python 3.x
- **Ghostscript**: External executable. Must be installed and accessible via PATH or bundled under `vendor\ghostscript`.
- **Tesseract OCR**: External executable. OCRmyPDF needs it for OCR work.
- **pngquant**: External executable. OCRmyPDF needs it when this script uses `--optimize 3`.
- Python packages from `requirements.txt`.
- Use the project virtual environment (`C:\LocalVenvs\pdfconvert`) when running the script.

Create or repair the source-checkout Python environment:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Utils\pdfconvert\bootstrap.ps1"
```

Install the external `pngquant` executable globally with Chocolatey if you are not using the packaged installer:
```powershell
choco install pngquant -y
```

## Setup & Usage (Right-Click Method)

This is the recommended way to use the tool.

1.  **Install Dependencies**: Make sure Ghostscript, Tesseract, and pngquant are installed on your system, or use the packaged installer.
2.  **Add Context Menu**: Double-click `install_right_click_context.bat`. This prepares the Python environment and adds the "Convert to OCR (v6.1)" option to your right-click menu for PDF files.
3.  **Run**: In Explorer, select one or more PDFs, right-click, and choose **Convert to OCR (v6.1)**.
4.  **Results**: For each file processed, a new `*_OCR.pdf` file will be created in the same directory with the original file's Modified Date, and the original file will be moved into a new `Originals` subfolder.

For implementation details, see `RIGHT_CLICK_CONTEXT_MENU.md`.

## Core Files
- `pdf_automation_v6.1.py`: The main Python script containing all the logic.
- `run_single_pdf.bat`: A helper batch script that allows the context menu to reliably call the Python script with file paths that contain spaces.
- `install_right_click_context.bat`: Double-click installer for the Explorer right-click action.
- `uninstall_right_click_context.bat`: Double-click remover for the Explorer right-click action.
- `setup_installed_app.ps1`: Post-install setup used by the packaged Windows installer.
- `HOW_TO_USE.txt`: Short coworker-facing usage instructions installed with the packaged app.
- `installer/`: Inno Setup build files for creating `PDFConvertOCR-Setup-v6.1.1.exe`.
- `registry/add_OCR_context_v6.1.reg`: The registry file for creating the right-click context menu item.
- `archives/`: Contains archived scripts and logs from previous versions.

## Building the Windows Installer

Install Inno Setup 6 on the build machine, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
```

The build script prepares an offline vendor payload from the local build machine and writes:

```text
dist\PDFConvertOCR-Setup-v6.1.1.exe
```

Review third-party licenses before distributing the installer, especially Ghostscript's AGPL/commercial licensing.

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
- `--optimize 3` requires the external `pngquant.exe` program; it is not a Python package and does not belong in `requirements.txt`.
- `--output-type pdf` writes standard searchable PDF output.

### Dependency Resolution
- The script checks for Ghostscript, Tesseract, pngquant, and OCRmyPDF before processing.
- The script prefers `ocrmypdf.exe` from the **active Python environment** first (for example `C:\LocalVenvs\pdfconvert\Scripts\ocrmypdf.exe` or an installed `python\Scripts\ocrmypdf.exe`) before searching system PATH.
- This prevents global/user Python package conflicts from breaking OCR when the project venv is healthy.
- Packaged installs prepend bundled runtime folders to PATH so OCRmyPDF can launch Ghostscript, Tesseract, and pngquant.

### Page Numbering
After OCR, PyMuPDF is used to add "Page X of Y" to the bottom center of each page.

### Modified Date
After OCR and page numbering are complete, the script sets the generated `*_OCR.pdf` file's Modified Date to match the source PDF.

### Temp files and originals
- Intermediate files live in a temporary directory and are cleaned after each file.
- Originals are archived with a timestamp and short UUID suffix to prevent name collisions (`<name>_YYYYMMDD_HHMMSS_<id>.pdf`).

## Troubleshooting
- **Script fails silently**: The most common cause is a missing dependency. Ensure both Ghostscript and Tesseract are installed and their paths are correctly configured in your system's environment variables.
- **`Could not find program 'pngquant' on the PATH`**:
  - Cause: OCRmyPDF needs the external `pngquant.exe` tool when the script uses `--optimize 3`.
  - Fix:
  ```powershell
  choco install pngquant -y
  ```
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
