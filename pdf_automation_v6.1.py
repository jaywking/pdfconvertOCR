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
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF

# ---------- Configuration ----------
APP_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.environ.get("PDFCONVERTOCR_BASE_DIR", APP_DIR))
SOURCE_DIR = BASE_DIR
PROCESSED_DIR = BASE_DIR / "_processed"
COMPLETE_DIR = BASE_DIR / "_complete"
LOG_DIR = BASE_DIR / "logs"

GHOSTSCRIPT_EXE = ""  # Populated by find_executable
OCR_MY_PDF_EXE = ""   # Populated by find_executable
TESSERACT_EXE = ""    # Populated by find_executable
PNGQUANT_EXE = ""     # Populated by find_executable
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

def find_executable(
    name: str,
    friendly_name: str,
    search_paths: list[Path],
    prefer_search_paths: bool = False,
) -> str:
    """Find an executable in common locations."""
    def find_in_search_paths() -> str:
        # Use rglob to find the executable in subdirectories.
        for base_path in search_paths:
            if not base_path.exists():
                continue
            if base_path.is_file() and base_path.name.lower() == name.lower():
                return str(base_path)
            direct = base_path / name
            if direct.exists():
                return str(direct)
            results = list(base_path.rglob(name))
            if results:
                return str(results[0])
        return ""

    if prefer_search_paths:
        found_path = find_in_search_paths()
        if found_path:
            logging.info(f"  ✅ Found {friendly_name} via bundled/common path: {found_path}")
            return found_path

    found_path = shutil.which(name)
    if found_path:
        logging.info(f"  ✅ Found {friendly_name} in PATH: {found_path}")
        return found_path

    if not prefer_search_paths:
        found_path = find_in_search_paths()
        if found_path:
            logging.info(f"  ✅ Found {friendly_name} via auto-detect: {found_path}")
            return found_path

    logging.error(f"  ❌ Missing dependency: {friendly_name} not found in PATH or common directories.")
    return ""

def ensure_executable_dir_on_path(exe_path: str) -> None:
    """Make auto-detected tool folders visible to child processes."""
    if not exe_path:
        return
    exe_dir = str(Path(exe_path).resolve().parent)
    current_path = os.environ.get("PATH", "")
    path_parts = [p for p in current_path.split(os.pathsep) if p]
    if exe_dir.lower() not in {p.lower() for p in path_parts}:
        os.environ["PATH"] = exe_dir + os.pathsep + current_path
        logging.info(f"  ✅ Added dependency folder to PATH for this run: {exe_dir}")

def check_dependencies() -> bool:
    """Check if required command-line tools are installed."""
    global GHOSTSCRIPT_EXE, OCR_MY_PDF_EXE, TESSERACT_EXE, PNGQUANT_EXE
    logging.info("🔎 Checking for dependencies...")

    # Define search paths for each executable
    gs_paths = [
        APP_DIR / "vendor" / "ghostscript" / "bin",
        APP_DIR / "vendor" / "ghostscript",
        Path(r"C:\\Program Files\\gs"),
        Path(r"C:\\Program Files (x86)\\gs")
    ]
    ocr_paths = [
        APP_DIR / "python" / "Scripts",
        Path(r"C:\\Users"), # Search all user profiles
        Path(r"C:\\Program Files")
    ]
    tesseract_paths = [
        APP_DIR / "vendor" / "tesseract",
        Path(r"C:\\Program Files\\Tesseract-OCR"),
        Path(r"C:\\Program Files")
    ]
    pngquant_paths = [
        APP_DIR / "vendor" / "pngquant",
        Path(r"C:\\ProgramData\\chocolatey\\bin"),
        Path(r"C:\\ProgramData\\chocolatey\\lib"),
        Path(r"C:\\Program Files")
    ]

    GHOSTSCRIPT_EXE = find_executable("gswin64c.exe", "Ghostscript", gs_paths, prefer_search_paths=True)
    TESSERACT_EXE = find_executable("tesseract.exe", "Tesseract OCR", tesseract_paths, prefer_search_paths=True)
    PNGQUANT_EXE = find_executable("pngquant.exe", "pngquant", pngquant_paths, prefer_search_paths=True)

    # Prefer OCRmyPDF from the active Python environment to avoid PATH collisions
    # (e.g., global/user installs shadowing this project's venv).
    env_ocr = Path(sys.executable).resolve().parent / "ocrmypdf.exe"
    env_scripts_ocr = Path(sys.executable).resolve().parent / "Scripts" / "ocrmypdf.exe"
    if env_ocr.exists():
        OCR_MY_PDF_EXE = str(env_ocr)
        logging.info(f"  ✅ Found OCRmyPDF in active environment: {OCR_MY_PDF_EXE}")
    elif env_scripts_ocr.exists():
        OCR_MY_PDF_EXE = str(env_scripts_ocr)
        logging.info(f"  ✅ Found OCRmyPDF in active environment Scripts folder: {OCR_MY_PDF_EXE}")
    else:
        OCR_MY_PDF_EXE = find_executable("ocrmypdf.exe", "OCRmyPDF", ocr_paths)

    if not all((GHOSTSCRIPT_EXE, OCR_MY_PDF_EXE, TESSERACT_EXE, PNGQUANT_EXE)):
        logging.error("Please install missing dependencies or add them to your system's PATH.")
        if not PNGQUANT_EXE:
            logging.error("pngquant is required by OCRmyPDF when using --optimize 3. Install it with: choco install pngquant")
        return False

    ensure_executable_dir_on_path(TESSERACT_EXE)
    ensure_executable_dir_on_path(PNGQUANT_EXE)
    ensure_executable_dir_on_path(GHOSTSCRIPT_EXE)
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





def ocr_pdf(src: str, dst: str) -> tuple[bool, str | None]:
    """Run OCRmyPDF with size-optimized settings and clear logging."""
    cmd = [
        OCR_MY_PDF_EXE,
        "--skip-text",          # only OCR pages without an existing text layer
        "--optimize", "3",
        "--jpeg-quality", "40",
        "--output-type", "pdf",
        "--deskew",
        src, dst,
    ]
    logging.info(f"Starting OCR step for: {Path(src).name}")
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # tolerate non-UTF8 output from child process
            timeout=OCR_TIMEOUT_SECS,
        )
        if "skipping all processing" in result.stdout:
            logging.info("PDF is already searchable. OCR not required.")
        else:
            logging.info("OCR completed successfully.")
        logging.info(f"OCR output generated: {Path(dst).name}")
        return True, None
    except subprocess.CalledProcessError as e:
        cmdline = subprocess.list2cmdline(cmd)
        logging.error(
            "OCRmyPDF failed on %s.\n   Command: %s\n   Return Code: %s\n   STDOUT: %s\n   STDERR: %s",
            Path(src).name,
            cmdline,
            e.returncode,
            e.stdout,
            e.stderr,
        )
        return False, f"OCR failed (rc={e.returncode})"
    except Exception as exc:
        logging.error("OCRmyPDF unexpected failure on %s: %s", Path(src).name, exc)
        return False, str(exc)

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



def archive_original(src: Path, archive_dir: Path) -> Path:
    """Move the original PDF into the archive with a unique, deterministic name."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    dest = archive_dir / f"{safe_filename(src.stem)}_{timestamp}_{unique}{src.suffix}"
    return Path(shutil.move(src, dest))

def preserve_modified_time(dst: Path, source_stat: os.stat_result) -> None:
    """Set the generated PDF's Modified Date to match the source PDF."""
    os.utime(dst, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    modified = datetime.fromtimestamp(source_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"Preserved Modified Date on {dst.name}: {modified}")

# ---------- Core Processing Logic ----------


def _process_one_pdf(
    source_path: Path,
    output_dir: Path,
    archive_dir: Path,
    temp_dir: Path,
    results: list[dict] | None = None,
) -> None:
    """Core logic to unlock, OCR, and archive a single PDF."""
    start_time = time.monotonic()
    success = False
    error: str | None = None
    pages: int | None = None
    unlocked = False
    source_stat = source_path.stat()

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_dir) as tmp_dir:
        stem = safe_filename(source_path.stem)
        unlocked_pdf = Path(tmp_dir) / f"{stem}_unlocked.pdf"
        final_ocr_pdf = output_dir / f"{stem}_OCR.pdf"

        work_file = source_path
        try:
            if is_pdf_locked(source_path):
                unlock_pdf(str(source_path), str(unlocked_pdf))
                work_file = unlocked_pdf
                unlocked = True
            else:
                logging.info(f"PDF '{source_path.name}' not locked; skipping unlock step")

            ocr_ok, ocr_err = ocr_pdf(str(work_file), str(final_ocr_pdf))
            if not ocr_ok:
                error = ocr_err or "OCR failed"
                logging.error(f"OCR step failed for {source_path.name}: {error}")
                if final_ocr_pdf.exists():
                    final_ocr_pdf.unlink()
                return

            if not add_page_numbers(final_ocr_pdf):
                logging.warning(f"Could not add page numbers to {final_ocr_pdf.name}, but continuing.")

            try:
                with fitz.open(str(final_ocr_pdf)) as doc:
                    pages = len(doc)
            except Exception as exc:
                logging.warning(f"Could not count pages for {final_ocr_pdf.name}: {exc}")

            preserve_modified_time(final_ocr_pdf, source_stat)

            archived_path = archive_original(source_path, archive_dir)
            logging.info(f"Original '{source_path.name}' moved to {archived_path.parent}")
            success = True
        except Exception as exc:
            error = str(exc)
            logging.error(f"Failed on {source_path.name}: {exc}")
        finally:
            duration = time.monotonic() - start_time
            status_label = "OK" if success else "FAIL"
            logging.info(
                f"Summary [{status_label}] {source_path.name} | pages={pages if pages is not None else '?'} | "
                f"unlocked={'yes' if unlocked else 'no'} | time={duration:.1f}s"
            )
            if results is not None:
                results.append(
                    {
                        "file": source_path.name,
                        "status": "ok" if success else "failed",
                        "pages": pages,
                        "duration_s": duration,
                        "unlocked": unlocked,
                        "error": error,
                    }
                )



def log_run_summary(results: list[dict]) -> None:
    """Log a concise summary for a run."""
    if not results:
        return
    total = len(results)
    failures = [r for r in results if r.get("status") != "ok"]
    logging.info(
        "Run summary: %s file(s) | succeeded=%s | failed=%s",
        total,
        total - len(failures),
        len(failures),
    )
    for r in results:
        err_text = f" | error={r['error']}" if r.get('error') else ""
        pages = r.get("pages")
        logging.info(
            "  [%s] %s | pages=%s | unlocked=%s | time=%.1fs%s",
            r.get("status", "?").upper(),
            r.get("file", ""),
            pages if pages is not None else "?",
            "yes" if r.get("unlocked") else "no",
            r.get("duration_s", 0.0),
            err_text,
        )

# ---------- Mode-specific Wrappers ----------


def process_single(file_path: Path) -> None:
    """Process one PDF in place and archive original."""
    base_dir = file_path.parent
    originals = base_dir / "Originals"
    results: list[dict] = []
    _process_one_pdf(file_path, base_dir, originals, base_dir, results)
    log_run_summary(results)


def process_batch() -> None:
    """Process all PDFs inside SOURCE_DIR."""
    if not SOURCE_DIR.is_dir():
        logging.error(f"Source directory not found: {SOURCE_DIR!s}")
        return

    pdfs = list(SOURCE_DIR.glob("*.pdf"))

    if not pdfs:
        logging.info("No PDFs found - nothing to do.")
        return

    logging.info(f"Found {len(pdfs)} PDF(s): {[p.name for p in pdfs]}")

    results: list[dict] = []
    for idx, path in enumerate(pdfs, 1):
        logging.info(f"[{idx}/{len(pdfs)}] {path.name}")
        try:
            _process_one_pdf(path, COMPLETE_DIR, PROCESSED_DIR, SOURCE_DIR, results)
        except Exception as exc:
            logging.error(f"Failed on {path.name}: {exc}")
    log_run_summary(results)

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
