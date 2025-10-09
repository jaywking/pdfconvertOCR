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
BASE_DIR = Path(r"C:\Utils\pdfconvert")
SOURCE_DIR = BASE_DIR
PROCESSED_DIR = BASE_DIR / "_processed"
COMPLETE_DIR = BASE_DIR / "_complete"
LOG_DIR = BASE_DIR / "logs"

GHOSTSCRIPT_EXE = "gswin64c.exe"   # Requires Ghostscript in PATH
OCR_MY_PDF_EXE = "ocrmypdf"       # Requires OCRmyPDF in PATH

# Page numbering settings
PAGE_NUMBER_FONT = "helv"  # Helvetica
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

def check_dependencies() -> bool:
    """Check if required command-line tools are installed and in the PATH."""
    logging.info("🔎 Checking for dependencies...")
    ok = True
    for exe in (GHOSTSCRIPT_EXE, OCR_MY_PDF_EXE):
        if shutil.which(exe):
            logging.info(f"  ✅ Found {exe}")
        else:
            logging.error(f"  ❌ Missing dependency: {exe} is not in your system's PATH.")
            ok = False
    if not ok:
        logging.error("Please install the missing dependencies and ensure they are in your PATH.")
    return ok

def is_pdf_locked(path: Path) -> bool:
    """Return True if print/copy is restricted or PDF is encrypted."""
    try:
        doc = fitz.open(path)
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
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180, encoding='utf-8')
        logging.info("✅ Unlock complete")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Ghostscript failed on {src}.\n"
                      f"   STDOUT: {e.stdout}\n"
                      f"   STDERR: {e.stderr}")
        raise

def ocr_pdf(src: str, dst: str) -> None:
    """Run OCRmyPDF with size-optimized settings."""
    cmd = [
        OCR_MY_PDF_EXE,
        "--skip-text",          # only pages without text
        "--optimize", "3",
        "--jpeg-quality", "40",
        "--remove-background",
        "--output-type", "pdf",
        "--deskew",
        src, dst
    ]
    logging.info(f"🔍 OCR start: {src}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        logging.info(f"✅ OCR output: {dst}")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ OCRmyPDF failed on {src}.\n"
                      f"   STDOUT: {e.stdout}\n"
                      f"   STDERR: {e.stderr}")
        raise

def add_page_numbers(pdf_path: Path) -> bool:
    """Adds 'Page X of Y' to the bottom center of each page."""
    logging.info(f"🔢 Adding page numbers to {pdf_path.name}")
    numbered_pdf_path = pdf_path.with_suffix(".numbered.pdf")
    try:
        doc = fitz.open(str(pdf_path))
        for i, page in enumerate(doc):
            # Define the rectangle for the page number at the bottom center
            footer_rect = fitz.Rect(0, page.rect.height - PAGE_NUMBER_Y_OFFSET, page.rect.width, page.rect.height)
            page_text = PAGE_NUMBER_FORMAT.format(page_num=i + 1, total_pages=len(doc))
            page.insert_textbox(
                footer_rect,
                page_text,
                fontsize=PAGE_NUMBER_FONTSIZE,
                fontname=PAGE_NUMBER_FONT,
                align=fitz.TEXT_ALIGN_CENTER,
                color=(0, 0, 0),  # Black
            )
        # Saving to a new file is more robust than overwriting, especially after OCRmyPDF.
        doc.save(str(numbered_pdf_path), garbage=4, deflate=True, clean=True)
        doc.close()
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