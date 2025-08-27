
# PDF Automation (Unlock + OCR) — v5

A Windows-friendly tool that unlocks restricted PDFs and runs OCR with size‑aware compression. It supports both batch processing from a working folder and a right‑click Explorer action for one or many PDFs.

## What it does
- Detects print or copy‑restricted PDFs and **unlocks** them using Ghostscript (silent, no prompts).
- Runs **OCR** with OCRmyPDF while **skipping pages that already contain text**.
- Uses compression settings that keep files reasonably small while staying readable by ChatGPT and other tools.
- Supports two modes:
  - **Batch mode** (no arguments): scans `C:\Utils\pdfconvert` and writes results to `_complete\`, originals to `_processed\`.
  - **Right‑click mode** (Explorer): processes selected PDFs **in place**, writes `*_OCR.pdf` next to each original, and moves each original into an `Originals\` subfolder.

## Requirements
- Windows 10 or 11
- Python 3.x
- **Ghostscript** in PATH (`gswin64c.exe`)
- **Tesseract OCR** in PATH (used by OCRmyPDF)
- Python packages: **OCRmyPDF**, **PyMuPDF**

Install Python packages:
```bat
pip install ocrmypdf PyMuPDF
```

## Files in this repo
- `pdf_automation_v5.py` — main script (dual mode).
- `run_pdfconvert_v5.bat` — launcher that forwards any selected files to the script.
- `registry\add_OCR_context_template.reg` — context‑menu template. Edit the path to your BAT, then import.
- `.gitignore`, `requirements.txt`.

## Quick start

### Batch mode (no arguments)
1. Place PDFs in `C:\Utils\pdfconvert`.
2. Run `run_pdfconvert_v5.bat` (or run `python pdf_automation_v5.py`).
3. Results:
   - Final OCR PDFs → `C:\Utils\pdfconvert\_complete\*`
   - Originals archived → `C:\Utils\pdfconvert\_processed\*`
   - Logs → `C:\Utils\pdfconvert\logs\*`

### Right‑click in Explorer (one or many PDFs)
1. Open `registry\add_OCR_context_template.reg` in a text editor and set the full path to your `run_pdfconvert_v5.bat`.
2. Double‑click the `.reg` file to import.
3. In Explorer, select one or many PDFs → right‑click → **Convert to OCR (v5)**.
4. Results (per file):
   - Output → `filename_OCR.pdf` next to the original
   - Original moved to `Originals\filename.pdf`

**Note**: The registry template uses `MultiSelectModel="Document"` so the menu shows up even when you select more than 15 files. Explorer will invoke the command once per selected file with `%1`.

## How it works

### Unlock check
The script opens the PDF with PyMuPDF and checks permissions for printing and copying. If restricted, it creates an unrestricted copy with Ghostscript:
```
gswin64c.exe -o unlocked.pdf -sDEVICE=pdfwrite -dPDFSETTINGS=/default input.pdf
```

### OCR with compression
OCR is performed with OCRmyPDF using settings that preserve text quality and reduce size:
```
--skip-text --optimize 3 --jpeg-quality 40 --remove-background --output-type pdf --deskew
```
- `--skip-text` avoids unnecessary OCR on pages that already contain searchable text.
- `--output-type pdf` keeps files smaller than PDF/A while remaining readable by ChatGPT.
- `--optimize 3` and `--jpeg-quality 40` reduce image size. Lower `jpeg-quality` gives smaller files with more visible compression.

### Mode behavior
- **Batch mode** writes output to `_complete\` and moves the originals to `_processed\`.
- **Right‑click mode** writes output next to each original and moves each original to an `Originals\` subfolder inside the same directory.

## Configuration
- Default working folder: `C:\Utils\pdfconvert`. Change `BASE_DIR` in the script if you prefer a different location.
- Ensure `gswin64c.exe` and `tesseract.exe` are in your PATH, or update `GHOSTSCRIPT_EXE` in the script.

## Troubleshooting
- **Menu disappears when selecting many files**: ensure the registry entry includes `MultiSelectModel="Document"` and the command uses `%1` (Explorer runs the command once per file).
- **File not detected in batch mode**: if using OneDrive Files On‑Demand, right‑click the file in Explorer and select **Always keep on this device**, then try again.
- **ChatGPT says “No text can be extracted from this file”**: re‑OCR with a fresh text layer:
  ```bat
  ocrmypdf --force-ocr --output-type pdf "input.pdf" "fixed.pdf"
  ```
  This increases size, so run your normal pipeline again afterward to apply compression if needed.
- **Ghostscript not found**: install Ghostscript and verify `gswin64c.exe` is in PATH. Update `GHOSTSCRIPT_EXE` in the script if necessary.
- **Tesseract not found**: install Tesseract and ensure it is in PATH. OCRmyPDF depends on it.

## Size tips
If output is still larger than you like, try:
- Lowering `--jpeg-quality` to `35` or `30` (trade‑off: more visible compression).
- Keeping `--output-type pdf` instead of PDF/A. Use PDF/A only when archival compliance is required.

## License
Choose a license for the repository (MIT is common for utility scripts). Add it as `LICENSE` in the repo root.
