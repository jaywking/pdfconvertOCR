# PDF Automation (Unlock + OCR) — v6.2

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

1. Download `PDFConvertOCR-Setup-v6.2.1.exe`.
2. Double-click the installer.
3. Right-click a PDF and choose **Convert to OCR (v6.2)**.

The installer is designed to install per-user under `%LOCALAPPDATA%\PDFConvertOCR`, bundle the OCR runtime tools, and create the right-click menu automatically. Before it executes or installs a bundled runtime, setup verifies the approved payload inventory, SHA-256 tree digests, and Python installer signature. A changed, missing, extra, or reparse-point-backed payload stops installation.

## How To Use It

PDFConvertOCR runs from Windows File Explorer. It does not open as a normal desktop app.

1. Open the folder that contains the PDF.
2. Right-click the PDF file.
3. Choose **Convert to OCR (v6.2)**.
4. Wait for the conversion window to finish.

The tool creates a searchable `*_OCR.pdf` next to the selected PDF, keeps the source file's Modified Date, and moves the original into an `Originals\` folder only after the output is fully verified.

## Source Checkout Requirements
- Windows 10 or 11
- The exact approved source Python runtime recorded in `trusted-artifacts.json`
  (currently PSF Python 3.14.4 on this workstation).
- **Ghostscript**: External executable. Must be installed and accessible via PATH or bundled under `vendor\ghostscript`.
- **Tesseract OCR**: External executable. OCRmyPDF needs it for OCR work.
- **pngquant**: External executable. OCRmyPDF needs it when this script uses `--optimize 3`.
- Python packages from the fully transitive, SHA-256-locked `requirements-lock.txt`.
- Use the project virtual environment (`C:\LocalVenvs\pdfconvertOCR`) when running the script.

Create the source-checkout Python environment, or reinstall its locked packages:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Utils\pdfconvertOCR\bootstrap.ps1"
```

Verify the approved source runtime and existing project environment without
installing packages:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Utils\pdfconvertOCR\bootstrap.ps1" -VerifyOnly
```

If verification reports that the existing project environment is not the
approved one, review the error and recreate it explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Utils\pdfconvertOCR\bootstrap.ps1" -Recreate
```

Bootstrap does not fall back to `py.exe`, an arbitrary `python.exe`, or an
unrelated virtual environment. The approved source Python and project runtime
are recorded in `trusted-artifacts.json`.

Install the external `pngquant` executable globally with Chocolatey if you are not using the packaged installer:
```powershell
choco install pngquant -y
```

## Setup & Usage (Right-Click Method)

This is the recommended way to use the tool.

1.  **Install Dependencies**: Make sure Ghostscript, Tesseract, and pngquant are installed on your system, or use the packaged installer.
2.  **Add Context Menu**: Double-click `install_right_click_context.bat`. This prepares the Python environment and adds the "Convert to OCR (v6.2)" option to your right-click menu for PDF files.
3.  **Run**: In Explorer, select one or more PDFs, right-click, and choose **Convert to OCR (v6.2)**.
4.  **Results**: For each file processed, a new `*_OCR.pdf` file will be created in the same directory with the original file's Modified Date. Only after that output is verified will the original be moved into a new `Originals` subfolder.

For implementation details, see `RIGHT_CLICK_CONTEXT_MENU.md`.

## Output Safety and Original Handling

PDFConvertOCR never overwrites an existing OCR output. If `Report_OCR.pdf`
already exists, the next conversion produces `Report_OCR (1).pdf` (then `(2)`,
and so on). Output is written to a temporary staging file, validated, and only
then published. If OCR, page numbering, or validation fails, the original and
existing outputs are left untouched.

Explorer right-click conversion keeps the default behavior: after a verified
output is published, the source PDF is moved into `Originals\` with a unique
archive name. For command-line use, choose a different source-file policy:

```powershell
# Default: move the source into Originals after verification
python .\pdf_automation_v6.2.py "C:\Docs\Report.pdf"

# Keep the source where it is
python .\pdf_automation_v6.2.py --original-action keep "C:\Docs\Report.pdf"

# Copy the source into Originals while retaining the source in place
python .\pdf_automation_v6.2.py --original-action copy "C:\Docs\Report.pdf"
```

Valid values for `--original-action` are `move`, `copy`, and `keep`.

## OCR Quality and Language Options

When you start a conversion from File Explorer, PDFConvertOCR shows a small
conversion-options prompt before any files are changed. Choose one quality
preset and one or more installed OCR languages:

- **Standard:** the existing balanced conversion: deskew, optimized PDF, and
  JPEG quality 40.
- **Straighten and rotate:** Standard plus automatic page-orientation
  correction.
- **Small file:** Standard processing with JPEG quality 25 for smaller output.
- **Archival PDF/A:** OCRmyPDF-generated PDF/A output for archival workflows.
  It intentionally omits page numbers so the archival output is not modified
  afterward. PDFConvertOCR does not independently certify PDF/A conformance.

English is selected by default. The prompt lists language packs detected from
the installed Tesseract runtime; select more than one when a document mixes
languages. The packaged installer includes English and orientation data only.
Additional packs must already be installed with Tesseract.

For non-interactive command-line or batch use, suppress the prompt and select
the same options explicitly:

```powershell
python .\pdf_automation_v6.2.py --no-options-prompt --quality-preset straighten-rotate --language eng "C:\Docs\Scan.pdf"
python .\pdf_automation_v6.2.py --no-options-prompt --quality-preset small-file --language eng "C:\Docs\Scan.pdf"
python .\pdf_automation_v6.2.py --no-options-prompt --quality-preset archival-pdfa --language eng "C:\Docs\Archive.pdf"
```

Use `--language eng+fra` for multiple installed language packs. Batch mode is
non-interactive and defaults to Standard with English unless options are given.

## Core Files
- `app_metadata.json`: The shared source of truth for app version, Explorer menu label, registry verb, runner script, and main script names.
- `pdf_automation_v6.2.py`: The main Python script containing all the logic.
- `run_single_pdf.bat`: A helper batch script that allows the context menu to reliably call the Python script with file paths that contain spaces.
- `install_right_click_context.bat`: Double-click installer for the Explorer right-click action.
- `uninstall_right_click_context.bat`: Double-click remover for the Explorer right-click action.
- `requirements-lock.txt`: Fully transitive Windows CPython 3.14 dependency lock with a SHA-256 hash for every accepted distribution.
- `trusted-artifacts.json`: Reviewed versions, source locations, file hashes, tree hashes, and signer requirements for build and packaged runtime inputs.
- `trusted_artifacts.ps1`: Shared fail-closed verification functions for file hashes, directory inventories, reparse points, and Authenticode signers.
- `setup_installed_app.ps1`: Post-install setup and repair script that verifies all packaged payloads before replacing the local Python runtime and installing the locked wheels.
- `HOW_TO_USE.txt`: Short coworker-facing usage instructions installed with the packaged app.
- `installer/`: Inno Setup build files for creating `PDFConvertOCR-Setup-v6.2.1.exe`.
- `registry/add_OCR_context_v6.2.reg`: The registry file for creating the right-click context menu item.
- `archives/`: Contains archived scripts and logs from previous versions.

## Building the Windows Installer

Install Inno Setup 6 on the build machine, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
```

To verify the currently approved build tools and staged vendor payload without
refreshing the payload or compiling an installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 -VerifyOnly
```

To compile from an already staged payload, use `-SkipVendorRefresh`. This does
not skip integrity checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 -SkipVendorRefresh
```

The build script prepares an offline vendor payload from the local build machine and writes:

```text
dist\PDFConvertOCR-Setup-v6.2.1.exe
```

`app_metadata.json` controls the app version, installer output name prefix, Explorer menu label, registry verb, and script filenames used by the source installer scripts and packaged installer build.

`requirements.txt` routes ordinary pip usage through the secure lock and records
the two direct application dependencies in comments. `requirements-lock.txt`
pins and hashes the complete Windows CPython 3.14
dependency set. `trusted-artifacts.json` separately pins the Python installer,
wheelhouse, Ghostscript, Tesseract, and pngquant payloads. The build verifies
those inputs and the signed Python/Inno Setup executables before execution or
packaging. `-SkipVendorRefresh` reuses the local staging tree only after the
same complete verification; `-VerifyOnly` performs the checks without compiling.

When intentionally changing a dependency, Python version, native runtime, or
build tool, independently verify its upstream provenance, update
`requirements-lock.txt` and/or `trusted-artifacts.json` as applicable, rebuild
the vendor payload, and review the resulting manifest and lock-file diff before
distributing a new installer. Do not update a digest merely to make an
unexpected local payload pass.

The packaged runtime is pinned to Python 3.14.7. The build script derives the
CPython feature and ABI wheel target from that version, and packaged upgrades
delete the prior staged vendor trees before copying the new payload. Installed
setup verifies all bundled payloads before execution, removes the prior local
Python runtime, installs the approved runtime, installs only the complete
hash-locked offline wheel set, and verifies required imports. The offline Python
payload includes Tcl/Tk because the Explorer conversion-options dialog uses
`tkinter`.

### Integrity and executable trust boundaries

- Source bootstrap accepts only the approved signed CPython installation and
  project environment recorded in `trusted-artifacts.json`.
- Installer creation verifies the source Python components, isolated build
  `pip`, Inno Setup signer, downloaded Python installer, and complete vendor
  directory inventories before compilation.
- Packaged setup performs the same vendor inventory checks before running the
  Python installer or importing a package. Verification failures stop setup;
  there is no network or unpinned-package fallback.
- Runtime OCR accepts `ocrmypdf.exe` only from the packaged
  `python\Scripts` directory or `C:\LocalVenvs\pdfconvertOCR\Scripts` and
  rejects a trusted runtime path containing a symlink or Windows reparse point.
- Ghostscript, Tesseract, and pngquant may still come from the documented
  system locations in a source checkout. Packaged installs prepend their
  verified bundled directories to `PATH`.

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
ocrmypdf.exe -l eng --skip-text --optimize 3 --jpeg-quality 40 --output-type pdf --deskew input.pdf output.pdf
```
- `--skip-text` OCRs only pages that do not already have text.
- `--optimize 3` and `--jpeg-quality 40` prioritize smaller output size.
- `--optimize 3` requires the external `pngquant.exe` program; it is not a Python package and does not belong in `requirements.txt`.
- `--output-type pdf` writes standard searchable PDF output.
- **Straighten and rotate** adds `--rotate-pages`; **Small file** changes JPEG
  quality to 25; **Archival PDF/A** uses `--output-type pdfa` and skips page
  numbering to avoid modifying that output afterward.

### Dependency Resolution
- The script checks for Ghostscript, Tesseract, pngquant, and OCRmyPDF before processing.
- The script accepts `ocrmypdf.exe` only from the packaged `python\Scripts`
  directory or `C:\LocalVenvs\pdfconvertOCR\Scripts`.
- PATH entries, other user profiles, unrelated environments, and recursive
  executable searches are not accepted for OCRmyPDF.
- A symlink, junction, or other Windows reparse point in either approved
  OCRmyPDF runtime path is rejected.
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
- **Packaged right-click install fails with `ModuleNotFoundError: No module named 'fitz'`**: Rerun the installer or run `setup_installed_app.ps1` from `%LOCALAPPDATA%\PDFConvertOCR`. It verifies every bundled payload, replaces the Python runtime from the approved offline installer, and installs the complete hash-locked wheel set.
- **Setup or build reports an integrity, digest, reparse-point, or signer failure**: Stop and obtain a fresh trusted installer or restore the reviewed build input. Do not bypass the check or update `trusted-artifacts.json` until the changed artifact's provenance has been independently verified.
- **Source bootstrap rejects the Python environment**: Run `bootstrap.ps1 -VerifyOnly` for the exact mismatch. If the approved source runtime is intact but `C:\LocalVenvs\pdfconvertOCR` is stale or damaged, rerun with `-Recreate`.
- **OCRmyPDF is reported missing even though another copy is on PATH**: PATH copies are intentionally ignored. Run `bootstrap.ps1` for a source checkout or rerun packaged setup so OCRmyPDF is installed in an approved runtime.
- **`Could not find program 'pngquant' on the PATH`**:
  - Cause: OCRmyPDF needs the external `pngquant.exe` tool when the script uses `--optimize 3`.
  - Fix:
  ```powershell
  choco install pngquant -y
  ```
- **`SystemError` about `pydantic-core` incompatibility**: Repair the approved
  runtime with `bootstrap.ps1 -Recreate` for a source checkout or rerun packaged
  setup. Global or user-level Python packages are not supported runtime inputs.
- **ChatGPT says "No text can be extracted"**: For a stubborn file, you can force re-OCR on every page with this manual command, though it may increase file size:
  ```bat
  ocrmypdf --force-ocr --output-type pdf "input.pdf" "fixed.pdf"
  ```
- **Want to tweak quality**: Adjust `--jpeg-quality` (e.g., 75 for smaller files or 95 for higher quality).
