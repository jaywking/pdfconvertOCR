#!/usr/bin/env python
# pdf_automation_v5.py
# ------------------------------------------------------------
# Dual-mode PDF unlock + OCR tool
#  • Batch: run without args – processes every .pdf in SOURCE_DIR
#  • Single: run with a file path (e.g. via Explorer context menu)
# ------------------------------------------------------------

import os
import sys
import shutil
import subprocess
import logging
import re
from datetime import datetime
import fitz  # PyMuPDF

# ---------- Configuration ----------
BASE_DIR        = r"C:\Utils\pdfconvert"
SOURCE_DIR      = BASE_DIR
PROCESSED_DIR   = os.path.join(BASE_DIR, "_processed")
COMPLETE_DIR    = os.path.join(BASE_DIR, "_complete")
LOG_DIR         = os.path.join(BASE_DIR, "logs")

GHOSTSCRIPT_EXE = "gswin64c.exe"   # Requires Ghostscript in PATH
OCR_MY_PDF_EXE  = "ocrmypdf"       # Requires OCRmyPDF in PATH

# ---------- One-time directory bootstrapping ----------
for d in (PROCESSED_DIR, COMPLETE_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)

# ---------- Logging ----------
log_file = os.path.join(LOG_DIR, datetime.now().strftime("log_%Y-%m-%d_%H%M.txt"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"),
              logging.StreamHandler()]
)

# ---------- Helper functions ----------
_illegal = re.compile(r'[<>:"/\\|?*]')


def safe_filename(name: str) -> str:
    """Strip illegal Win characters from filename stem."""
    return _illegal.sub("_", name)


def is_pdf_locked(path: str) -> bool:
    """Return True if print/copy is restricted."""
    try:
        doc = fitz.open(path)
        can_print = doc.permissions & fitz.PDF_PERM_PRINT
        can_copy  = doc.permissions & fitz.PDF_PERM_COPY
        return not (can_print and can_copy)
    except Exception as exc:
        logging.error(f"Permission check failed: {exc}")
        return False


def unlock_pdf(src: str, dst: str) -> None:
    """Re-write PDF with Ghostscript to remove restrictions."""
    logging.info(f"🔓 Unlocking via Ghostscript: {src}")
    cmd = [GHOSTSCRIPT_EXE, "-o", dst, "-sDEVICE=pdfwrite",
           "-dPDFSETTINGS=/default", src]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    logging.info("✅ Unlock complete")


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
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    logging.info(f"✅ OCR output: {dst}")


# ---------- Single-file (right-click) path ----------
def process_single(file_path: str) -> None:
    """Process one PDF in place and archive original."""
    base_dir  = os.path.dirname(file_path)
    originals = os.path.join(base_dir, "Originals")
    os.makedirs(originals, exist_ok=True)

    stem          = safe_filename(os.path.splitext(os.path.basename(file_path))[0])
    unlocked_pdf  = os.path.join(base_dir, f"{stem}_unlocked.pdf")
    final_ocr_pdf = os.path.join(base_dir, f"{stem}_OCR.pdf")

    work_file = file_path
    try:
        if is_pdf_locked(file_path):
            unlock_pdf(file_path, unlocked_pdf)
            work_file = unlocked_pdf
        else:
            logging.info("PDF not locked; skipping unlock step")

        ocr_pdf(work_file, final_ocr_pdf)

        shutil.move(file_path, os.path.join(originals, os.path.basename(file_path)))
        logging.info(f"📦 Original moved to {originals}")

    finally:
        if os.path.exists(unlocked_pdf):
            os.remove(unlocked_pdf)


# ---------- Batch mode path ----------
def process_batch() -> None:
    """Process all PDFs inside SOURCE_DIR (legacy behaviour)."""
    try:
        pdfs = [f for f in os.listdir(SOURCE_DIR)
                if f.lower().endswith(".pdf") and
                   os.path.isfile(os.path.join(SOURCE_DIR, f))]
    except FileNotFoundError:
        logging.error(f"Source directory not found: {SOURCE_DIR}")
        return

    if not pdfs:
        logging.info("No PDFs found – nothing to do.")
        return

    logging.info(f"Found {len(pdfs)} PDF(s): {pdfs}")

    for idx, fname in enumerate(pdfs, 1):
        path = os.path.join(SOURCE_DIR, fname)
        logging.info(f"▶ [{idx}/{len(pdfs)}] {fname}")
        try:
            process_dir_managed(path)
        except Exception as exc:
            logging.error(f"❌ Failed on {fname}: {exc}")


def process_dir_managed(file_path: str) -> None:
    """Old per-file logic that uses _processed/_complete directories."""
    stem          = safe_filename(os.path.splitext(os.path.basename(file_path))[0])
    unlocked_pdf  = os.path.join(SOURCE_DIR,  f"{stem}_unlocked.pdf")
    final_ocr_pdf = os.path.join(COMPLETE_DIR, f"{stem}_OCR.pdf")

    work_file = file_path
    try:
        if is_pdf_locked(file_path):
            unlock_pdf(file_path, unlocked_pdf)
            work_file = unlocked_pdf
        ocr_pdf(work_file, final_ocr_pdf)
        shutil.move(file_path, os.path.join(PROCESSED_DIR, os.path.basename(file_path)))
    finally:
        if os.path.exists(unlocked_pdf):
            os.remove(unlocked_pdf)


# ---------- Main dispatcher ----------
def main() -> None:
    logging.info("🚀 PDF Automation start")

    # Were any file paths passed (right-click context)?
    if len(sys.argv) >= 2:
        pdfs = [p for p in sys.argv[1:] if p.lower().endswith(".pdf")]
        if pdfs:
            for p in pdfs:
                if os.path.isfile(p):
                    logging.info(f"Right-click mode on {p}")
                    process_single(os.path.abspath(p))
                else:
                    logging.error(f"File not found: {p}")
            return
        # If args were passed but none are PDFs, just exit
        logging.error("No valid PDFs in argument list.")
        return

    # No args → legacy batch mode
    process_batch()
    logging.info("🏁 Finished")

if __name__ == "__main__":
    main()
