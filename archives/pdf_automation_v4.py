import os
import shutil
import subprocess
import logging
import time
import re
from datetime import datetime
import fitz  # PyMuPDF

# --- Configuration ---
BASE_DIR = r"C:\Utils\pdfconvert"
SOURCE_DIR = BASE_DIR
PROCESSED_DIR = os.path.join(BASE_DIR, "_processed")
COMPLETE_DIR = os.path.join(BASE_DIR, "_complete")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# --- NEW: GHOSTSCRIPT CONFIGURATION ---
# You must install Ghostscript: https://www.ghostscript.com/releases/gsdnld.html
# Set this to the name of the executable (if in PATH) or the full path to it.
GHOSTSCRIPT_EXE = "gswin64c.exe"

OCR_MY_PDF_EXE = r"ocrmypdf"

# --- Ensure required directories exist ---
for directory in [PROCESSED_DIR, COMPLETE_DIR, LOG_DIR]:
    os.makedirs(directory, exist_ok=True)

# --- Logging Setup ---
log_filename = datetime.now().strftime("log_%Y-%m-%d_%H%M.txt")
LOG_FILE = os.path.join(LOG_DIR, log_filename)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def safe_filename(name):
    """Removes illegal characters from a filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def is_pdf_locked(pdf_path):
    """Checks if a PDF has print or copy restrictions."""
    try:
        doc = fitz.open(pdf_path)
        can_print = doc.permissions & fitz.PDF_PERM_PRINT
        can_copy = doc.permissions & fitz.PDF_PERM_COPY
        if not (can_print and can_copy):
            return True  # It is locked
        return False  # It is not locked
    except Exception as e:
        logging.error(f"❌ Error checking permissions for {pdf_path}: {e}")
        return False

def unlock_pdf(input_pdf, output_pdf):
    """
    Unlocks a PDF by re-processing it with Ghostscript.
    This is a reliable alternative to printing.
    """
    try:
        logging.info(f"✨ Unlocking with Ghostscript: {input_pdf}")
        cmd = [
            GHOSTSCRIPT_EXE,
            "-o", output_pdf,
            "-sDEVICE=pdfwrite",
            "-dPDFSETTINGS=/default",
            input_pdf
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
        logging.info(f"✅ Ghostscript unlock complete: {output_pdf}")
    except FileNotFoundError:
        logging.error("❌ Ghostscript not found. Please install it and check the GHOSTSCRIPT_EXE path.")
        raise
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Ghostscript failed while processing {input_pdf}.")
        logging.error(f"GHOSTSCRIPT STDERR: {e.stderr}")
        raise

def ocr_pdf(input_pdf, output_pdf):
    """Runs OCRmyPDF on a given PDF file, skipping pages that already have text."""
    try:
        cmd = [
            OCR_MY_PDF_EXE,
            "--skip-text",  # This new argument solves the "page already has text" error
            "--optimize", "2",
            "--deskew",
            "--output-type", "pdfa",
            input_pdf,
            output_pdf
        ]
        logging.info(f"🔍 Running OCR (with --skip-text) on: {input_pdf}")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logging.info(f"✅ OCR complete: {output_pdf}")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Error during OCR of {input_pdf}: {e}")
        logging.error(f"OCR STDOUT: {e.stdout}")
        logging.error(f"OCR STDERR: {e.stderr}")
        raise

def process_pdf(file_path):
    """Main processing logic for a single PDF file."""
    base_raw = os.path.splitext(os.path.basename(file_path))[0]
    base_name = safe_filename(base_raw)
    
    unlocked_pdf = os.path.join(SOURCE_DIR, f"{base_name}_unlocked.pdf")
    final_ocr_pdf = os.path.join(COMPLETE_DIR, f"{base_name}_OCR.pdf")
    
    processing_file = file_path # Start with the original file

    try:
        if is_pdf_locked(file_path):
            logging.info(f"🔒 Locked PDF detected, unlocking with Ghostscript: {file_path}")
            unlock_pdf(file_path, unlocked_pdf)
            processing_file = unlocked_pdf # The next step will use the unlocked file
        else:
            logging.info(f"✅ Unlocked PDF, proceeding directly to OCR: {file_path}")
        
        logging.info(f"🔍 Starting OCR on: {processing_file}")
        ocr_pdf(processing_file, final_ocr_pdf)
        
        # Move the original file to the processed directory after successful OCR
        shutil.move(file_path, os.path.join(PROCESSED_DIR, os.path.basename(file_path)))
        logging.info(f"Moved original file to processed: {os.path.basename(file_path)}")

    finally:
        # Cleanup the intermediate unlocked file if it exists
        if os.path.exists(unlocked_pdf):
            os.remove(unlocked_pdf)
            logging.info(f"🧹 Cleaned up intermediate file: {unlocked_pdf}")

def main():
    """Main function to find and process PDF files."""
    print("🟢 MAIN FUNCTION STARTED", flush=True)
    logging.info("🚀 PDF Automation process started.")
    
    try:
        pdf_files = [
            f for f in os.listdir(SOURCE_DIR)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(SOURCE_DIR, f))
        ]
    except FileNotFoundError:
        logging.error(f"❌ Source directory not found: {SOURCE_DIR}")
        return

    logging.info(f"📊 Found {len(pdf_files)} PDF(s) to process: {pdf_files}")

    if not pdf_files:
        logging.info("📂 No new PDFs found to process.")
        return

    for idx, file in enumerate(pdf_files, start=1):
        file_path = os.path.join(SOURCE_DIR, file)
        print(f"\n📄 Processing {idx}/{len(pdf_files)}: {file}", flush=True)
        logging.info(f"📄 Processing {idx}/{len(pdf_files)}: {file}")
        try:
            process_pdf(file_path)
            logging.info(f"✅ Successfully processed: {file}")
        except Exception as e:
            print(f"❌ An error occurred while processing {file}. Check logs for details.", flush=True)
            logging.error(f"❌ FAILED to process {file_path}: {e}")

    logging.info("✅ PDF Automation process finished.")

if __name__ == "__main__":
    main()
