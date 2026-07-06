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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF

# ---------- Configuration ----------
GS_TIMEOUT_SECS = 600
OCR_TIMEOUT_SECS = 600

# Page numbering settings
PAGE_NUMBER_FONT = "helv"  # Helvetica
PAGE_NUMBER_FONT_FALLBACK = "cobe" # Courier
PAGE_NUMBER_FONTSIZE = 8
PAGE_NUMBER_Y_OFFSET = 20  # Distance from bottom of page
PAGE_NUMBER_FORMAT = "Page {page_num} of {total_pages}"


@dataclass(frozen=True)
class AppConfig:
    app_dir: Path
    base_dir: Path
    source_dir: Path
    processed_dir: Path
    complete_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class RuntimeTools:
    ghostscript: str
    ocrmypdf: str
    tesseract: str
    pngquant: str


@dataclass
class ProcessResult:
    file: str
    status: str
    pages: int | None
    duration_s: float
    unlocked: bool
    error: str | None = None


def build_config() -> AppConfig:
    """Build runtime paths without touching the filesystem."""
    app_dir = Path(__file__).resolve().parent
    base_dir = Path(os.environ.get("PDFCONVERTOCR_BASE_DIR", app_dir))
    return AppConfig(
        app_dir=app_dir,
        base_dir=base_dir,
        source_dir=base_dir,
        processed_dir=base_dir / "_processed",
        complete_dir=base_dir / "_complete",
        log_dir=base_dir / "logs",
    )


def ensure_runtime_dirs(config: AppConfig) -> None:
    """Create folders used by batch mode and logging."""
    for d in (config.processed_dir, config.complete_dir, config.log_dir):
        d.mkdir(parents=True, exist_ok=True)


def configure_logging(config: AppConfig) -> None:
    """Configure per-run logging after runtime paths are known."""
    log_file = config.log_dir / datetime.now().strftime("log_%Y-%m-%d_%H%M.txt")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ],
        force=True,
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

def check_dependencies(config: AppConfig) -> RuntimeTools | None:
    """Check if required command-line tools are installed."""
    logging.info("🔎 Checking for dependencies...")

    # Define search paths for each executable
    gs_paths = [
        config.app_dir / "vendor" / "ghostscript" / "bin",
        config.app_dir / "vendor" / "ghostscript",
        Path(r"C:\\Program Files\\gs"),
        Path(r"C:\\Program Files (x86)\\gs")
    ]
    ocr_paths = [
        config.app_dir / "python" / "Scripts",
        Path(r"C:\\Users"), # Search all user profiles
        Path(r"C:\\Program Files")
    ]
    tesseract_paths = [
        config.app_dir / "vendor" / "tesseract",
        Path(r"C:\\Program Files\\Tesseract-OCR"),
        Path(r"C:\\Program Files")
    ]
    pngquant_paths = [
        config.app_dir / "vendor" / "pngquant",
        Path(r"C:\\ProgramData\\chocolatey\\bin"),
        Path(r"C:\\ProgramData\\chocolatey\\lib"),
        Path(r"C:\\Program Files")
    ]

    ghostscript_exe = find_executable("gswin64c.exe", "Ghostscript", gs_paths, prefer_search_paths=True)
    tesseract_exe = find_executable("tesseract.exe", "Tesseract OCR", tesseract_paths, prefer_search_paths=True)
    pngquant_exe = find_executable("pngquant.exe", "pngquant", pngquant_paths, prefer_search_paths=True)

    # Prefer OCRmyPDF from the active Python environment to avoid PATH collisions
    # (e.g., global/user installs shadowing this project's venv).
    env_ocr = Path(sys.executable).resolve().parent / "ocrmypdf.exe"
    env_scripts_ocr = Path(sys.executable).resolve().parent / "Scripts" / "ocrmypdf.exe"
    if env_ocr.exists():
        ocrmypdf_exe = str(env_ocr)
        logging.info(f"  ✅ Found OCRmyPDF in active environment: {ocrmypdf_exe}")
    elif env_scripts_ocr.exists():
        ocrmypdf_exe = str(env_scripts_ocr)
        logging.info(f"  ✅ Found OCRmyPDF in active environment Scripts folder: {ocrmypdf_exe}")
    else:
        ocrmypdf_exe = find_executable("ocrmypdf.exe", "OCRmyPDF", ocr_paths)

    if not all((ghostscript_exe, ocrmypdf_exe, tesseract_exe, pngquant_exe)):
        logging.error("Please install missing dependencies or add them to your system's PATH.")
        if not pngquant_exe:
            logging.error("pngquant is required by OCRmyPDF when using --optimize 3. Install it with: choco install pngquant")
        return None

    ensure_executable_dir_on_path(tesseract_exe)
    ensure_executable_dir_on_path(pngquant_exe)
    ensure_executable_dir_on_path(ghostscript_exe)
    return RuntimeTools(
        ghostscript=ghostscript_exe,
        ocrmypdf=ocrmypdf_exe,
        tesseract=tesseract_exe,
        pngquant=pngquant_exe,
    )

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

def unlock_pdf(src: str, dst: str, tools: RuntimeTools) -> None:
    """Re-write PDF with Ghostscript to remove restrictions."""
    logging.info(f"🔓 Unlocking via Ghostscript: {src}")
    cmd = [tools.ghostscript, "-o", dst, "-sDEVICE=pdfwrite",
           "-dPDFSETTINGS=/default", src]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=GS_TIMEOUT_SECS, encoding='utf-8')
        logging.info("✅ Unlock complete")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Ghostscript failed on {src}.\n" 
                      f"   STDOUT: {e.stdout}\n" 
                      f"   STDERR: {e.stderr}")
        raise





def ocr_pdf(src: str, dst: str, tools: RuntimeTools) -> tuple[bool, str | None]:
    """Run OCRmyPDF with size-optimized settings and clear logging."""
    cmd = [
        tools.ocrmypdf,
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
    tools: RuntimeTools,
) -> ProcessResult:
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
                unlock_pdf(str(source_path), str(unlocked_pdf), tools)
                work_file = unlocked_pdf
                unlocked = True
            else:
                logging.info(f"PDF '{source_path.name}' not locked; skipping unlock step")

            ocr_ok, ocr_err = ocr_pdf(str(work_file), str(final_ocr_pdf), tools)
            if not ocr_ok:
                error = ocr_err or "OCR failed"
                logging.error(f"OCR step failed for {source_path.name}: {error}")
                if final_ocr_pdf.exists():
                    final_ocr_pdf.unlink()
            else:
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

    duration = time.monotonic() - start_time
    status_label = "OK" if success else "FAIL"
    logging.info(
        f"Summary [{status_label}] {source_path.name} | pages={pages if pages is not None else '?'} | "
        f"unlocked={'yes' if unlocked else 'no'} | time={duration:.1f}s"
    )
    return ProcessResult(
        file=source_path.name,
        status="ok" if success else "failed",
        pages=pages,
        duration_s=duration,
        unlocked=unlocked,
        error=error,
    )


def log_run_summary(results: list[ProcessResult]) -> None:
    """Log a concise summary for a run."""
    if not results:
        return
    total = len(results)
    failures = [r for r in results if r.status != "ok"]
    logging.info(
        "Run summary: %s file(s) | succeeded=%s | failed=%s",
        total,
        total - len(failures),
        len(failures),
    )
    for r in results:
        err_text = f" | error={r.error}" if r.error else ""
        pages = r.pages
        logging.info(
            "  [%s] %s | pages=%s | unlocked=%s | time=%.1fs%s",
            r.status.upper(),
            r.file,
            pages if pages is not None else "?",
            "yes" if r.unlocked else "no",
            r.duration_s,
            err_text,
        )

# ---------- Mode-specific Wrappers ----------


def process_single(file_path: Path, tools: RuntimeTools) -> None:
    """Process one PDF in place and archive original."""
    base_dir = file_path.parent
    originals = base_dir / "Originals"
    result = _process_one_pdf(file_path, base_dir, originals, base_dir, tools)
    log_run_summary([result])


def process_batch(config: AppConfig, tools: RuntimeTools) -> None:
    """Process all PDFs inside SOURCE_DIR."""
    if not config.source_dir.is_dir():
        logging.error(f"Source directory not found: {config.source_dir!s}")
        return

    pdfs = list(config.source_dir.glob("*.pdf"))

    if not pdfs:
        logging.info("No PDFs found - nothing to do.")
        return

    logging.info(f"Found {len(pdfs)} PDF(s): {[p.name for p in pdfs]}")

    results: list[ProcessResult] = []
    for idx, path in enumerate(pdfs, 1):
        logging.info(f"[{idx}/{len(pdfs)}] {path.name}")
        try:
            results.append(_process_one_pdf(path, config.complete_dir, config.processed_dir, config.source_dir, tools))
        except Exception as exc:
            logging.error(f"Failed on {path.name}: {exc}")
            results.append(
                ProcessResult(
                    file=path.name,
                    status="failed",
                    pages=None,
                    duration_s=0.0,
                    unlocked=False,
                    error=str(exc),
                )
            )
    log_run_summary(results)

# ---------- Main dispatcher ----------
def main() -> None:
    config = build_config()
    ensure_runtime_dirs(config)
    configure_logging(config)

    logging.info("🚀 PDF Automation start (v6)")

    tools = check_dependencies(config)
    if tools is None:
        return  # Exit if dependencies are not met

    args = sys.argv[1:]
    pdf_args = [Path(p) for p in args if p.lower().endswith(".pdf")]

    if pdf_args:
        for p in pdf_args:
            if p.is_file():
                logging.info(f"Single-file mode on: {p!s}")
                process_single(p.resolve(), tools)
            else:
                logging.error(f"File not found: {p!s}")
    elif args:
        logging.error("No valid PDF files found in arguments.")
    else:
        # No args → legacy batch mode
        process_batch(config, tools)

    logging.info("🏁 Finished")

if __name__ == "__main__":
    main()
