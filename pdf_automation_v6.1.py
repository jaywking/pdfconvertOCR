#!/usr/bin/env python
# pdf_automation_v6.py
# ------------------------------------------------------------
# Dual-mode PDF unlock + OCR tool
#  • Batch: run without args – processes every .pdf in SOURCE_DIR
#  • Single: run with a file path (e.g. via Explorer context menu)
# ------------------------------------------------------------

import argparse
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
class QualityPreset:
    key: str
    label: str
    output_type: str
    jpeg_quality: int
    rotate_pages: bool = False
    add_page_numbers: bool = True
    archival: bool = False


QUALITY_PRESETS = {
    "standard": QualityPreset("standard", "Standard", "pdf", 40),
    "straighten-rotate": QualityPreset(
        "straighten-rotate", "Straighten and rotate", "pdf", 40, rotate_pages=True
    ),
    "archival-pdfa": QualityPreset(
        "archival-pdfa", "Archival PDF/A", "pdfa", 40, add_page_numbers=False, archival=True
    ),
    "small-file": QualityPreset("small-file", "Small file", "pdf", 25),
}


@dataclass(frozen=True)
class ConversionOptions:
    preset: QualityPreset
    languages: tuple[str, ...]


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
    output_path: str | None = None
    original_action: str = "move"
    original_result: str | None = None
    source_bytes: int | None = None
    output_bytes: int | None = None
    verified: bool = False
    quality_preset: str = "standard"
    languages: tuple[str, ...] = ("eng",)
    page_numbered: bool = False
    archival_output: bool = False
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


def parse_tesseract_languages(output: str) -> tuple[str, ...]:
    """Extract OCR language codes from `tesseract --list-langs` output."""
    languages: list[str] = []
    for raw_line in output.splitlines():
        code = raw_line.strip()
        if not code or code.lower().startswith("list of available languages"):
            continue
        if code == "osd":
            continue
        languages.append(code)
    return tuple(dict.fromkeys(languages))


def discover_tesseract_languages(tesseract_exe: str) -> tuple[str, ...]:
    """Return installed OCR languages, excluding orientation-only data."""
    try:
        result = subprocess.run(
            [tesseract_exe, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception as exc:
        raise RuntimeError(f"Could not list installed Tesseract languages: {exc}") from exc

    languages = parse_tesseract_languages(result.stdout)
    if not languages:
        raise RuntimeError("Tesseract reported no OCR language packs")
    return languages


def normalize_languages(value: str | None, available_languages: tuple[str, ...]) -> tuple[str, ...]:
    """Validate a plus-separated OCR language selection against installed packs."""
    selected = tuple(dict.fromkeys(part.strip() for part in (value or "eng").split("+") if part.strip()))
    if not selected:
        raise ValueError("Select at least one OCR language")
    unavailable = [code for code in selected if code not in available_languages]
    if unavailable:
        raise ValueError(
            "Requested OCR language pack(s) are not installed: " + ", ".join(unavailable)
        )
    return selected


def prompt_conversion_options(
    available_languages: tuple[str, ...],
    initial_preset: str,
    initial_languages: tuple[str, ...],
) -> ConversionOptions | None:
    """Show a conversion-only options prompt; None means the user cancelled."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise RuntimeError("This Python runtime cannot show the conversion options prompt") from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError(f"Could not open the conversion options prompt: {exc}") from exc

    root.title("PDFConvertOCR options")
    root.resizable(False, False)
    root.columnconfigure(0, weight=1)
    choice = tk.StringVar(value=initial_preset)
    language_vars = {
        code: tk.BooleanVar(value=code in initial_languages)
        for code in available_languages
    }
    result: dict[str, ConversionOptions | None] = {"value": None}

    frame = tk.Frame(root, padx=16, pady=12)
    frame.grid(sticky="nsew")
    tk.Label(frame, text="Quality preset").grid(row=0, column=0, sticky="w")
    for index, preset in enumerate(QUALITY_PRESETS.values(), 1):
        suffix = " (no page numbers)" if not preset.add_page_numbers else ""
        tk.Radiobutton(
            frame,
            text=f"{preset.label}{suffix}",
            variable=choice,
            value=preset.key,
        ).grid(row=index, column=0, sticky="w")

    language_row = len(QUALITY_PRESETS) + 1
    tk.Label(frame, text="OCR languages").grid(row=language_row, column=0, sticky="w", pady=(10, 0))
    for index, code in enumerate(available_languages, language_row + 1):
        label = "eng (English)" if code == "eng" else code
        tk.Checkbutton(frame, text=label, variable=language_vars[code]).grid(row=index, column=0, sticky="w")

    def convert() -> None:
        selected_languages = tuple(code for code, variable in language_vars.items() if variable.get())
        if not selected_languages:
            messagebox.showerror("PDFConvertOCR", "Select at least one OCR language.", parent=root)
            return
        result["value"] = ConversionOptions(QUALITY_PRESETS[choice.get()], selected_languages)
        root.destroy()

    def cancel() -> None:
        root.destroy()

    button_row = language_row + len(available_languages) + 1
    buttons = tk.Frame(frame)
    buttons.grid(row=button_row, column=0, sticky="e", pady=(12, 0))
    tk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
    tk.Button(buttons, text="Convert", command=convert, default="active").pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()
    return result["value"]


def resolve_conversion_options(
    tools: RuntimeTools,
    preset_key: str | None,
    language_value: str | None,
    show_prompt: bool,
) -> ConversionOptions | None:
    """Resolve validated CLI or dialog selections before any file is processed."""
    available_languages = discover_tesseract_languages(tools.tesseract)
    initial_key = preset_key or "standard"
    initial_languages = normalize_languages(language_value, available_languages)
    if show_prompt:
        return prompt_conversion_options(available_languages, initial_key, initial_languages)
    return ConversionOptions(QUALITY_PRESETS[initial_key], initial_languages)

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





def build_ocr_command(src: str, dst: str, tools: RuntimeTools, options: ConversionOptions) -> list[str]:
    """Build the OCRmyPDF command for a named, safe quality preset."""
    preset = options.preset
    cmd = [
        tools.ocrmypdf,
        "-l", "+".join(options.languages),
        "--skip-text",          # only OCR pages without an existing text layer
        "--optimize", "3",
        "--jpeg-quality", str(preset.jpeg_quality),
        "--output-type", preset.output_type,
        "--deskew",
    ]
    if preset.rotate_pages:
        cmd.append("--rotate-pages")
    return [*cmd, src, dst]


def ocr_pdf(
    src: str,
    dst: str,
    tools: RuntimeTools,
    options: ConversionOptions,
) -> tuple[bool, str | None]:
    """Run OCRmyPDF with the selected preset and languages."""
    cmd = build_ocr_command(src, dst, tools, options)
    logging.info(f"Starting OCR step for: {Path(src).name}")
    logging.info(
        "OCR settings: preset=%s | languages=%s",
        options.preset.key,
        "+".join(options.languages),
    )
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

def add_page_numbers(source_pdf: Path, numbered_pdf: Path) -> bool:
    """Write a separately numbered PDF without modifying the OCR source file."""
    logging.info(f"🔢 Adding page numbers to {source_pdf.name}")
    try:
        with fitz.open(str(source_pdf)) as doc:
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

            doc.save(str(numbered_pdf), garbage=4, deflate=True, clean=True)
        return True
    except Exception as exc:
        logging.error(f"❌ Failed to add page numbers to {source_pdf.name}: {exc}")
        if numbered_pdf.exists():
            numbered_pdf.unlink()
        return False



def unique_archive_path(src: Path, archive_dir: Path) -> Path:
    """Return a collision-proof archive destination for an original PDF."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    return archive_dir / f"{safe_filename(src.stem)}_{timestamp}_{unique}{src.suffix}"


def apply_original_action(src: Path, archive_dir: Path, action: str) -> str:
    """Apply the requested source-file policy after output publication."""
    if action == "keep":
        return "kept in place"

    dest = unique_archive_path(src, archive_dir)
    if action == "copy":
        shutil.copy2(src, dest)
        return f"copied to {dest}"
    if action == "move":
        shutil.move(src, dest)
        return f"moved to {dest}"
    raise ValueError(f"Unsupported original action: {action}")


def staging_pdf_path(output_dir: Path, stem: str, label: str) -> Path:
    """Create a unique hidden staging path on the same volume as final output."""
    return output_dir / f".{stem}.{label}.{uuid.uuid4().hex}.pdf"


def next_output_path(output_dir: Path, stem: str) -> Path:
    """Return the first available sibling output name without overwriting files."""
    base_name = f"{stem}_OCR"
    candidate = output_dir / f"{base_name}.pdf"
    index = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name} ({index}).pdf"
        index += 1
    return candidate


def publish_staged_output(staged_path: Path, output_dir: Path, stem: str) -> Path:
    """Publish a staged file without replacing an existing output."""
    while True:
        candidate = next_output_path(output_dir, stem)
        try:
            # Hard-link creation is atomic and refuses an existing destination.
            # Both paths are in output_dir, so they are guaranteed to share a volume.
            os.link(staged_path, candidate)
            staged_path.unlink()
            return candidate
        except FileExistsError:
            logging.info("Output collision for %s; choosing another name.", candidate.name)


def page_is_nonblank(page: fitz.Page) -> bool:
    """Detect pages that should produce OCR text, including scanned-image pages."""
    return bool(
        page.get_text("text").strip()
        or page.get_images(full=True)
        or page.get_drawings()
    )


def validate_ocr_text(source_pdf: Path, ocr_pdf_path: Path) -> tuple[bool, str | None, int]:
    """Require OCR text for each non-blank source page before page numbers are added."""
    try:
        with fitz.open(source_pdf) as source_doc, fitz.open(ocr_pdf_path) as ocr_doc:
            if len(source_doc) != len(ocr_doc):
                return False, "OCR output page count does not match the source", 0
            text_pages = 0
            for index, (source_page, ocr_page) in enumerate(zip(source_doc, ocr_doc), 1):
                extracted = ocr_page.get_text("text").strip()
                if extracted:
                    text_pages += 1
                if page_is_nonblank(source_page) and not extracted:
                    return False, f"OCR text missing on non-blank page {index}", text_pages
            return True, None, text_pages
    except Exception as exc:
        return False, f"Could not validate OCR text: {exc}", 0


def validate_final_output(final_pdf: Path, expected_pages: int, source_stat: os.stat_result) -> tuple[bool, str | None]:
    """Validate the finalized staged output before it is published."""
    try:
        if not final_pdf.is_file() or final_pdf.stat().st_size == 0:
            return False, "Final output is missing or empty"
        with fitz.open(final_pdf) as doc:
            if len(doc) != expected_pages:
                return False, "Final output page count does not match the source"
        if final_pdf.stat().st_mtime_ns != source_stat.st_mtime_ns:
            return False, "Final output modified timestamp does not match the source"
        return True, None
    except Exception as exc:
        return False, f"Could not validate final output: {exc}"

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
    original_action: str = "move",
    conversion_options: ConversionOptions | None = None,
) -> ProcessResult:
    """Create a verified OCR output, then apply the requested source-file action."""
    start_time = time.monotonic()
    success = False
    error: str | None = None
    pages: int | None = None
    unlocked = False
    source_stat = source_path.stat()
    source_bytes = source_stat.st_size
    output_path: Path | None = None
    output_bytes: int | None = None
    verified = False
    original_result: str | None = None
    conversion_options = conversion_options or ConversionOptions(QUALITY_PRESETS["standard"], ("eng",))
    page_numbered = False

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_dir) as tmp_dir:
        stem = safe_filename(source_path.stem)
        unlocked_pdf = Path(tmp_dir) / f"{stem}_unlocked.pdf"
        ocr_staged_pdf = staging_pdf_path(output_dir, stem, "ocr")
        numbered_staged_pdf = staging_pdf_path(output_dir, stem, "numbered")

        work_file = source_path
        try:
            if is_pdf_locked(source_path):
                unlock_pdf(str(source_path), str(unlocked_pdf), tools)
                work_file = unlocked_pdf
                unlocked = True
            else:
                logging.info(f"PDF '{source_path.name}' not locked; skipping unlock step")

            ocr_ok, ocr_err = ocr_pdf(str(work_file), str(ocr_staged_pdf), tools, conversion_options)
            if not ocr_ok:
                error = ocr_err or "OCR failed"
                logging.error(f"OCR step failed for {source_path.name}: {error}")
            else:
                text_ok, text_error, text_pages = validate_ocr_text(work_file, ocr_staged_pdf)
                if not text_ok:
                    error = text_error or "OCR text validation failed"
                else:
                    staged_final_pdf = ocr_staged_pdf
                    if conversion_options.preset.add_page_numbers:
                        if not add_page_numbers(ocr_staged_pdf, numbered_staged_pdf):
                            error = "Page numbering failed"
                        else:
                            staged_final_pdf = numbered_staged_pdf
                            page_numbered = True
                    if error:
                        pass
                    else:
                        preserve_modified_time(staged_final_pdf, source_stat)
                        with fitz.open(work_file) as doc:
                            pages = len(doc)
                        final_ok, final_error = validate_final_output(staged_final_pdf, pages, source_stat)
                        if not final_ok:
                            error = final_error or "Final output validation failed"
                        else:
                            verified = True
                            output_path = publish_staged_output(staged_final_pdf, output_dir, stem)
                            output_bytes = output_path.stat().st_size
                            logging.info(
                                "Verified output published: %s | text_pages=%s | bytes=%s",
                                output_path.name,
                                text_pages,
                                output_bytes,
                            )
                            try:
                                original_result = apply_original_action(source_path, archive_dir, original_action)
                                logging.info("Original '%s' %s", source_path.name, original_result)
                                success = True
                            except Exception as action_exc:
                                error = f"Output published, but original action failed: {action_exc}"
                                logging.error(error)
        except Exception as exc:
            error = str(exc)
            logging.error(f"Failed on {source_path.name}: {exc}")
        finally:
            for staged_path in (ocr_staged_pdf, numbered_staged_pdf):
                if staged_path.exists():
                    staged_path.unlink()

    duration = time.monotonic() - start_time
    status_label = "OK" if success else "FAIL"
    logging.info(
        f"Summary [{status_label}] {source_path.name} | pages={pages if pages is not None else '?'} | "
        f"unlocked={'yes' if unlocked else 'no'} | verified={'yes' if verified else 'no'} | time={duration:.1f}s"
    )
    return ProcessResult(
        file=source_path.name,
        status="ok" if success else "failed",
        pages=pages,
        duration_s=duration,
        unlocked=unlocked,
        output_path=str(output_path) if output_path else None,
        original_action=original_action,
        original_result=original_result,
        source_bytes=source_bytes,
        output_bytes=output_bytes,
        verified=verified,
        quality_preset=conversion_options.preset.key,
        languages=conversion_options.languages,
        page_numbered=page_numbered,
        archival_output=conversion_options.preset.archival,
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
        output_text = f" | output={r.output_path}" if r.output_path else ""
        original_text = f" | original={r.original_result or r.original_action}"
        size_text = (
            f" | bytes={r.source_bytes}->{r.output_bytes}"
            if r.source_bytes is not None and r.output_bytes is not None
            else ""
        )
        quality_text = f" | preset={r.quality_preset} | languages={'+'.join(r.languages)}"
        numbering_text = f" | page_numbers={'yes' if r.page_numbered else 'no'}"
        archival_text = " | archival=OCRmyPDF-generated" if r.archival_output else ""
        logging.info(
            "  [%s] %s | pages=%s | unlocked=%s | verified=%s | time=%.1fs%s%s%s%s%s%s%s",
            r.status.upper(),
            r.file,
            pages if pages is not None else "?",
            "yes" if r.unlocked else "no",
            "yes" if r.verified else "no",
            r.duration_s,
            output_text,
            original_text,
            size_text,
            quality_text,
            numbering_text,
            archival_text,
            err_text,
        )

# ---------- Mode-specific Wrappers ----------


def process_single(
    file_path: Path,
    tools: RuntimeTools,
    original_action: str,
    conversion_options: ConversionOptions,
) -> None:
    """Process one PDF in place using the requested source-file policy."""
    base_dir = file_path.parent
    originals = base_dir / "Originals"
    result = _process_one_pdf(
        file_path,
        base_dir,
        originals,
        base_dir,
        tools,
        original_action,
        conversion_options,
    )
    log_run_summary([result])


def process_batch(
    config: AppConfig,
    tools: RuntimeTools,
    original_action: str,
    conversion_options: ConversionOptions,
) -> None:
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
            results.append(
                _process_one_pdf(
                    path,
                    config.complete_dir,
                    config.processed_dir,
                    config.source_dir,
                    tools,
                    original_action,
                    conversion_options,
                )
            )
        except Exception as exc:
            logging.error(f"Failed on {path.name}: {exc}")
            results.append(
                ProcessResult(
                    file=path.name,
                    status="failed",
                    pages=None,
                    duration_s=0.0,
                    unlocked=False,
                    original_action=original_action,
                    quality_preset=conversion_options.preset.key,
                    languages=conversion_options.languages,
                    archival_output=conversion_options.preset.archival,
                    error=str(exc),
                )
            )
    log_run_summary(results)

# ---------- Main dispatcher ----------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unlock and OCR PDFs while safely handling originals."
    )
    parser.add_argument(
        "--original-action",
        choices=("move", "copy", "keep"),
        default="move",
        help="What to do with a source after verified output is published (default: move).",
    )
    parser.add_argument(
        "--quality-preset",
        choices=tuple(QUALITY_PRESETS),
        help="OCR quality preset. Defaults to Standard when no prompt is shown.",
    )
    parser.add_argument(
        "--language",
        help="Installed Tesseract language code(s), joined with + (for example eng+fra).",
    )
    parser.add_argument(
        "--no-options-prompt",
        action="store_true",
        help="Do not show the conversion options prompt for selected files.",
    )
    parser.add_argument("pdf_files", nargs="*", type=Path, help="PDF files to process in place.")
    options = parser.parse_args()

    config = build_config()
    ensure_runtime_dirs(config)
    configure_logging(config)

    logging.info("🚀 PDF Automation start (v6)")

    tools = check_dependencies(config)
    if tools is None:
        return  # Exit if dependencies are not met

    pdf_args = options.pdf_files
    try:
        conversion_options = resolve_conversion_options(
            tools,
            options.quality_preset,
            options.language,
            show_prompt=bool(pdf_args) and not options.no_options_prompt,
        )
    except (RuntimeError, ValueError) as exc:
        logging.error("Could not resolve OCR options: %s", exc)
        return
    if conversion_options is None:
        logging.info("Conversion cancelled before any files were changed.")
        return

    if pdf_args:
        for p in pdf_args:
            if p.suffix.lower() != ".pdf":
                logging.error("Not a PDF file: %s", p)
            elif p.is_file():
                logging.info(f"Single-file mode on: {p!s}")
                process_single(p.resolve(), tools, options.original_action, conversion_options)
            else:
                logging.error(f"File not found: {p!s}")
    else:
        # No args → legacy batch mode
        process_batch(config, tools, options.original_action, conversion_options)

    logging.info("🏁 Finished")

if __name__ == "__main__":
    main()
