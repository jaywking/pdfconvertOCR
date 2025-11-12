#!/usr/bin/env python
# pdf_automation_v6.py
# ------------------------------------------------------------
# Dual-mode PDF unlock + OCR tool
#  • Batch: run without args – processes every .pdf in SOURCE_DIR
#  • Single: run with a file path (e.g. via Explorer context menu)
# ------------------------------------------------------------

import sys
import shutil
import subprocess
import logging
import re
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF

# ---------- Configuration ----------
BASE_DIR = Path(r"C:\\Utils\\pdfconvert")
SOURCE_DIR = BASE_DIR
PROCESSED_DIR = BASE_DIR / "_processed"
COMPLETE_DIR = BASE_DIR / "_complete"
LOG_DIR = BASE_DIR / "logs"

GHOSTSCRIPT_EXE = ""  # Populated by find_executable
OCR_MY_PDF_EXE = ""   # Populated by find_executable
GS_TIMEOUT_SECS = 600
OCR_TIMEOUT_SECS = 600

# Page numbering settings
PAGE_NUMBER_FONT = "helv"  # Helvetica
PAGE_NUMBER_FONT_FALLBACK = "cobe" # Courier
PAGE_NUMBER_FONTSIZE = 8
PAGE_NUMBER_Y_OFFSET = 20  # Distance from bottom of page
PAGE_NUMBER_FORMAT = "Page {page_num} of {total_pages}"

# ---------- One-time directory bootstrapping ----------
for d in (PROCESSED_DIR, COMPLETE_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------- Logging ----------
log_file = LOG_DIR / datetime.now().strftime("log_%Y-%m-%d_%H%M.txt")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ---------- Helper functions ----------
_illegal = re.compile(r'[<>:"/\\|?*]')

def safe_filename(name: str) -> str:
    """Strip illegal Win characters from filename stem."""
    return _illegal.sub("_", name)

def find_executable(name: str, friendly_name: str, search_paths: list[Path]) -> str:
    """Find an executable in common locations."""
    # 1. Check PATH first
    found_path = shutil.which(name)
    if found_path:
        logging.info(f"  ✅ Found {friendly_name} in PATH: {found_path}")
        return found_path

    # 2. Check common installation folders
    for base_path in search_paths:
        # Use rglob to find the executable in subdirectories
        results = list(base_path.rglob(name))
        if results:
            found_path = str(results[0])
            logging.info(f"  ✅ Found {friendly_name} via auto-detect: {found_path}")
            return found_path

    logging.error(f"  ❌ Missing dependency: {friendly_name} not found in PATH or common directories.")
    return ""

def check_dependencies() -> bool:
    """Check if required command-line tools are installed."""
    global GHOSTSCRIPT_EXE, OCR_MY_PDF_EXE
    logging.info("🔎 Checking for dependencies...")

    # Define search paths for each executable
    gs_paths = [
        Path(r"C:\\Program Files\\gs"),
        Path(r"C:\\Program Files (x86)\\gs")
    ]
    ocr_paths = [
        Path(r"C:\\Users"), # Search all user profiles
        Path(r"C:\\Program Files")
    ]

    GHOSTSCRIPT_EXE = find_executable("gswin64c.exe", "Ghostscript", gs_paths)
    OCR_MY_PDF_EXE = find_executable("ocrmypdf.exe", "OCRmyPDF", ocr_paths)

    if not all((GHOSTSCRIPT_EXE, OCR_MY_PDF_EXE)):
        logging.error("Please install missing dependencies or add them to your system's PATH.")
        return False

    return True

def is_pdf_locked(path: Path) -> bool:
    """Return True if print/copy is restricted or PDF is encrypted."""
    try:
        with fitz.open(path) as doc:
            # An encrypted PDF with no user password will also fail to open correctly
            # and is effectively "locked" for our purposes.
            if doc.is_encrypted and not doc.authenticate(''):
                return True
            can_print = doc.permissions & fitz.PDF_PERM_PRINT
            can_copy = doc.permissions & fitz.PDF_PERM_COPY
            return not (can_print and can_copy)
    except Exception as exc:
        logging.error(f"Permission check failed for {path.name}: {exc}")
        return False

def unlock_pdf(src: str, dst: str) -> None:
    """Re-write PDF with Ghostscript to remove restrictions."""
    logging.info(f"🔓 Unlocking via Ghostscript: {src}")
    cmd = [GHOSTSCRIPT_EXE, "-o", dst, "-sDEVICE=pdfwrite",
           "-dPDFSETTINGS=/default", src]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=GS_TIMEOUT_SECS, encoding='utf-8')
        logging.info("✅ Unlock complete")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Ghostscript failed on {src}.\n" 
                      f"   STDOUT: {e.stdout}\n" 
                      f"   STDERR: {e.stderr}")
        raise

def ocr_pdf(src: str, dst: str) -> None:
    """Run OCRmyPDF with size-optimized settings and clear logging."""
    cmd = [
        OCR_MY_PDF_EXE,
        "--skip-text",          # only pages without text
        "--optimize", "3",
        "--jpeg-quality", "40",
        "--output-type", "pdf",
        "--deskew",
        src, dst
    ]
    logging.info(f"🔍 Starting OCR step for: {Path(src).name}")
    try:
        # Run the command and capture all output.
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, 
            encoding='utf-8', timeout=OCR_TIMEOUT_SECS
        )
        # Check the output to see if OCR was skipped.
        if "skipping all processing" in result.stdout:
            logging.info("✅ PDF is already searchable. OCR not required.")
        else:
            logging.info("✅ OCR completed successfully.")
        logging.info(f"✅ OCR output generated: {Path(dst).name}")

    except subprocess.CalledProcessError as e:
        # Log the full error details if the process fails.
        logging.error(f"❌ OCRmyPDF failed on {Path(src).name}.\n" 
                      f"   Return Code: {e.returncode}\n" 
                      f"   STDOUT: {e.stdout}\n" 
                      f"   STDERR: {e.stderr}")
        raise

def add_page_numbers(pdf_path: Path) -> bool:
    """Adds 'Page X of Y' to the bottom center of each page."""
    logging.info(f"🔢 Adding page numbers to {pdf_path.name}")
    numbered_pdf_path = pdf_path.with_suffix(".numbered.pdf")
    try:
        with fitz.open(str(pdf_path)) as doc:
            for i, page in enumerate(doc):
                footer_rect = fitz.Rect(0, page.rect.height - PAGE_NUMBER_Y_OFFSET, page.rect.width, page.rect.height)
                page_text = PAGE_NUMBER_FORMAT.format(page_num=i + 1, total_pages=len(doc))
                try:
                    page.insert_textbox(
                        footer_rect,
                        page_text,
                        fontsize=PAGE_NUMBER_FONTSIZE,
                        fontname=PAGE_NUMBER_FONT,
                        align=fitz.TEXT_ALIGN_CENTER,
                        color=(0, 0, 0),  # Black
                    )
                except RuntimeError as e:
                    if "cannot find font" in str(e).lower():
                        logging.warning(f"Font '{PAGE_NUMBER_FONT}' not found, retrying with fallback '{PAGE_NUMBER_FONT_FALLBACK}'.")
                        page.insert_textbox(
                            footer_rect,
                            page_text,
                            fontsize=PAGE_NUMBER_FONTSIZE,
                            fontname=PAGE_NUMBER_FONT_FALLBACK,
                            align=fitz.TEXT_ALIGN_CENTER,
                            color=(0, 0, 0),  # Black
                        )
                    else:
                        raise # Re-raise other runtime errors

            doc.save(str(numbered_pdf_path), garbage=4, deflate=True, clean=True)
        pdf_path.unlink()  # Delete the original OCR'd file
        numbered_pdf_path.rename(pdf_path)  # Rename the new file to the original name
        return True
    except Exception as exc:
        logging.error(f"❌ Failed to add page numbers to {pdf_path.name}: {exc}")
        if numbered_pdf_path.exists():
            numbered_pdf_path.unlink()
        return False

# ---------- Core Processing Logic ----------
def _process_one_pdf(
    source_path: Path,
    output_dir: Path,
    archive_dir: Path,
    temp_dir: Path,
) -> None:
    """Core logic to unlock, OCR, and archive a single PDF."""
    stem = safe_filename(source_path.stem)
    unlocked_pdf = temp_dir / f"{stem}_unlocked.pdf"
    final_ocr_pdf = output_dir / f"{stem}_OCR.pdf"

    work_file = source_path
    try:
        if is_pdf_locked(source_path):
            unlock_pdf(str(source_path), str(unlocked_pdf))
            work_file = unlocked_pdf
        else:
            logging.info(f"PDF '{source_path.name}' not locked; skipping unlock step")

        ocr_pdf(str(work_file), str(final_ocr_pdf))

        if not add_page_numbers(final_ocr_pdf):
            logging.warning(f"Could not add page numbers to {final_ocr_pdf.name}, but continuing.")

        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(source_path, archive_dir / source_path.name)
        logging.info(f"📦 Original '{source_path.name}' moved to {archive_dir}")

    finally:
        if unlocked_pdf.exists():
            unlocked_pdf.unlink()
            logging.info(f"🧹 Cleaned up intermediate file: {unlocked_pdf.name}")

# ---------- Mode-specific Wrappers ----------
def process_single(file_path: Path) -> None:
    """Process one PDF in place and archive original."""
    base_dir = file_path.parent
    originals = base_dir / "Originals"
    _process_one_pdf(file_path, base_dir, originals, base_dir)

def process_batch() -> None:
    """Process all PDFs inside SOURCE_DIR."""
    if not SOURCE_DIR.is_dir():
        logging.error(f"Source directory not found: {SOURCE_DIR!s}")
        return

    pdfs = list(SOURCE_DIR.glob("*.pdf"))

    if not pdfs:
        logging.info("No PDFs found – nothing to do.")
        return

    logging.info(f"Found {len(pdfs)} PDF(s): {[p.name for p in pdfs]}")

    for idx, path in enumerate(pdfs, 1):
        logging.info(f"▶ [{idx}/{len(pdfs)}] {path.name}")
        try:
            _process_one_pdf(path, COMPLETE_DIR, PROCESSED_DIR, SOURCE_DIR)
        except Exception as exc:
            logging.error(f"❌ Failed on {path.name}: {exc}")

# ---------- Main dispatcher ----------
def main() -> None:
    logging.info("🚀 PDF Automation start (v6)")

    if not check_dependencies():
        return  # Exit if dependencies are not met

    args = sys.argv[1:]
    pdf_args = [Path(p) for p in args if p.lower().endswith(".pdf")]

    if pdf_args:
        for p in pdf_args:
            if p.is_file():
                logging.info(f"Single-file mode on: {p!s}")
                process_single(p.resolve())
            else:
                logging.error(f"File not found: {p!s}")
    elif args:
        logging.error("No valid PDF files found in arguments.")
    else:
        # No args → legacy batch mode
        process_batch()

    logging.info("🏁 Finished")

if __name__ == "__main__":
    main()
