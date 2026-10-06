#!/usr/bin/env python
# pdf_automation_v6.2.py
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
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import pymupdf as fitz

# ---------- Configuration ----------
GS_TIMEOUT_SECS = 600
OCR_TIMEOUT_SECS = 600
IO_REPARSE_TAG_NAME_SURROGATE = 0x20000000

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


@dataclass(frozen=True)
class PdfSourceIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    link_count: int


class UnsafePdfInputError(ValueError):
    """Raised when a PDF input cannot be tied to one stable ordinary file."""


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
    assert_no_redirecting_reparse_path(config.base_dir)
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


def trusted_ocrmypdf_roots(config: AppConfig) -> tuple[Path, ...]:
    """Return the only Python runtime roots approved to supply OCRmyPDF."""
    return (
        config.app_dir / "python",
        Path(r"C:\LocalVenvs\pdfconvertOCR"),
    )


def path_contains_reparse_point(path: Path) -> bool:
    """Return True when a Windows path or any existing parent is a link/junction."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        try:
            attributes = getattr(component.lstat(), "st_file_attributes", 0)
        except OSError:
            continue
        if attributes & reparse_flag:
            return True
    return False


def lexical_absolute_path(path: Path) -> Path:
    """Return an absolute path without resolving links or junctions."""
    return Path(os.path.abspath(os.fspath(path)))


def assert_no_redirecting_reparse_path(path: Path) -> None:
    """Reject symlinks, junctions, and redirecting Windows reparse points."""
    absolute = lexical_absolute_path(path)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for component in (absolute, *absolute.parents):
        try:
            component_stat = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise UnsafePdfInputError(
                f"Could not inspect PDF path component '{component}': {exc}"
            ) from exc

        if stat.S_ISLNK(component_stat.st_mode):
            raise UnsafePdfInputError(
                f"PDF input path contains a symbolic link: {component}"
            )

        attributes = getattr(component_stat, "st_file_attributes", 0)
        if not attributes & reparse_flag:
            continue

        reparse_tag = getattr(component_stat, "st_reparse_tag", 0)
        is_name_surrogate = not reparse_tag or bool(
            reparse_tag & IO_REPARSE_TAG_NAME_SURROGATE
        )
        if is_name_surrogate:
            raise UnsafePdfInputError(
                f"PDF input path contains a redirecting reparse point: {component}"
            )


def pdf_source_identity(
    source_path: Path,
    source_stat: os.stat_result,
) -> PdfSourceIdentity:
    """Build a stable identity for one ordinary, singly linked PDF file."""
    if not stat.S_ISREG(source_stat.st_mode):
        raise UnsafePdfInputError(f"PDF input is not a regular file: {source_path}")
    if source_stat.st_nlink != 1:
        raise UnsafePdfInputError(
            f"PDF input must have exactly one hard link; found {source_stat.st_nlink}: "
            f"{source_path}"
        )
    if not source_stat.st_ino:
        raise UnsafePdfInputError(
            f"The filesystem did not provide a stable file identity for: {source_path}"
        )
    return PdfSourceIdentity(
        device=source_stat.st_dev,
        inode=source_stat.st_ino,
        size=source_stat.st_size,
        modified_ns=source_stat.st_mtime_ns,
        link_count=source_stat.st_nlink,
    )


def inspect_pdf_input(
    source_path: Path,
) -> tuple[Path, os.stat_result, PdfSourceIdentity]:
    """Validate a PDF directory entry without following a link-backed leaf."""
    source_path = lexical_absolute_path(source_path)
    if source_path.suffix.lower() != ".pdf":
        raise UnsafePdfInputError(f"Not a PDF file: {source_path}")
    if os.name == "nt":
        _drive, path_without_drive = os.path.splitdrive(str(source_path))
        if ":" in path_without_drive:
            raise UnsafePdfInputError(
                f"NTFS alternate data stream paths are not supported: {source_path}"
            )

    assert_no_redirecting_reparse_path(source_path)
    try:
        source_stat = source_path.lstat()
    except FileNotFoundError as exc:
        raise UnsafePdfInputError(f"PDF input was not found: {source_path}") from exc
    except OSError as exc:
        raise UnsafePdfInputError(
            f"Could not inspect PDF input '{source_path}': {exc}"
        ) from exc
    return source_path, source_stat, pdf_source_identity(source_path, source_stat)


def assert_pdf_source_unchanged(
    source_path: Path,
    expected: PdfSourceIdentity,
    phase: str,
) -> None:
    """Fail when the selected PDF entry changes during processing."""
    _path, _source_stat, current = inspect_pdf_input(source_path)
    if current != expected:
        raise UnsafePdfInputError(
            f"PDF input changed before {phase}; output was not allowed to continue: "
            f"{source_path}"
        )


def stat_matches_pdf_identity(
    source_stat: os.stat_result,
    expected: PdfSourceIdentity,
) -> bool:
    """Compare stable file/content fields while allowing link-count transitions."""
    return (
        source_stat.st_dev == expected.device
        and source_stat.st_ino == expected.inode
        and source_stat.st_size == expected.size
        and source_stat.st_mtime_ns == expected.modified_ns
    )


def copy_pdf_source_snapshot(
    source_path: Path,
    snapshot_path: Path,
    expected: PdfSourceIdentity,
) -> None:
    """Copy from one verified open file into private processing storage."""
    try:
        with source_path.open("rb") as source_stream:
            opened = pdf_source_identity(source_path, os.fstat(source_stream.fileno()))
            if opened != expected:
                raise UnsafePdfInputError(
                    f"PDF input changed while it was being opened: {source_path}"
                )
            with snapshot_path.open("xb") as snapshot_stream:
                shutil.copyfileobj(source_stream, snapshot_stream)
            after_copy = pdf_source_identity(
                source_path, os.fstat(source_stream.fileno())
            )
            if after_copy != expected:
                raise UnsafePdfInputError(
                    f"PDF input changed while it was being copied: {source_path}"
                )
        assert_pdf_source_unchanged(source_path, expected, "processing")
    except Exception:
        if snapshot_path.exists():
            snapshot_path.unlink()
        raise


def find_trusted_ocrmypdf(config: AppConfig) -> str:
    """Resolve OCRmyPDF only from the two application-owned Python runtimes."""
    for runtime_root in trusted_ocrmypdf_roots(config):
        candidate = runtime_root / "Scripts" / "ocrmypdf.exe"
        if not candidate.is_file():
            continue
        if path_contains_reparse_point(runtime_root) or path_contains_reparse_point(candidate):
            logging.error("  ❌ Rejected linked OCRmyPDF runtime path: %s", candidate)
            continue
        try:
            resolved_root = runtime_root.resolve(strict=True)
            resolved_candidate = candidate.resolve(strict=True)
            resolved_candidate.relative_to(resolved_root)
        except (OSError, ValueError):
            logging.error("  ❌ Rejected OCRmyPDF outside trusted runtime: %s", candidate)
            continue
        if resolved_candidate.is_file():
            logging.info("  ✅ Found OCRmyPDF in trusted runtime: %s", resolved_candidate)
            return str(resolved_candidate)

    logging.error(
        "  ❌ Missing dependency: OCRmyPDF was not found in the packaged runtime "
        "or C:\\LocalVenvs\\pdfconvertOCR. Run bootstrap.ps1 or repair the packaged installation."
    )
    return ""

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

    ocrmypdf_exe = find_trusted_ocrmypdf(config)

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
        raise RuntimeError(
            "This Python runtime cannot show the conversion options prompt; "
            "reinstall PDFConvertOCR to repair bundled Tcl/Tk support"
        ) from exc

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


def apply_original_action(
    src: Path,
    archive_dir: Path,
    action: str,
    expected_identity: PdfSourceIdentity,
    stable_source: Path,
) -> str:
    """Apply the requested source-file policy after output publication."""
    if action == "keep":
        assert_pdf_source_unchanged(src, expected_identity, "the original-file action")
        return "kept in place"

    dest = unique_archive_path(src, archive_dir)
    assert_no_redirecting_reparse_path(archive_dir)
    if action == "copy":
        assert_pdf_source_unchanged(src, expected_identity, "the original-file copy")
        shutil.copy2(stable_source, dest)
        try:
            assert_pdf_source_unchanged(
                src, expected_identity, "completion of the original-file copy"
            )
        except Exception:
            if dest.exists():
                dest.unlink()
            raise
        return f"copied to {dest}"
    if action == "move":
        assert_pdf_source_unchanged(src, expected_identity, "the original-file move")
        shutil.move(src, dest)
        try:
            _dest_path, _dest_stat, moved_identity = inspect_pdf_input(dest)
            if moved_identity != expected_identity:
                raise UnsafePdfInputError(
                    f"PDF input changed during the original-file move: {src}"
                )
        except Exception:
            if dest.exists() and not src.exists():
                shutil.move(dest, src)
            raise
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


def publish_staged_output(
    staged_path: Path,
    output_dir: Path,
    stem: str,
    expected_identity: PdfSourceIdentity,
) -> Path:
    """Publish a staged file without replacing an existing output."""
    assert_pdf_source_unchanged(
        staged_path, expected_identity, "the staged-output publication"
    )
    while True:
        candidate = next_output_path(output_dir, stem)
        try:
            # Hard-link creation is atomic and refuses an existing destination.
            # Both paths are in output_dir, so they are guaranteed to share a volume.
            os.link(staged_path, candidate)
        except FileExistsError:
            logging.info("Output collision for %s; choosing another name.", candidate.name)
            continue

        staged_stat = staged_path.lstat()
        candidate_stat = candidate.lstat()
        if not (
            stat_matches_pdf_identity(staged_stat, expected_identity)
            and stat_matches_pdf_identity(candidate_stat, expected_identity)
            and os.path.samestat(staged_stat, candidate_stat)
        ):
            if os.path.samestat(staged_stat, candidate_stat):
                candidate.unlink()
            raise UnsafePdfInputError(
                f"Staged PDF changed during output publication: {staged_path}"
            )

        staged_path.unlink()
        _candidate_path, _candidate_stat, final_identity = inspect_pdf_input(candidate)
        if final_identity != expected_identity:
            candidate.unlink()
            raise UnsafePdfInputError(
                f"Published PDF identity did not match the validated output: {candidate}"
            )
        return candidate


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
    _temp_dir: Path,
    tools: RuntimeTools,
    original_action: str = "move",
    conversion_options: ConversionOptions | None = None,
) -> ProcessResult:
    """Create a verified OCR output, then apply the requested source-file action."""
    source_path = lexical_absolute_path(source_path)
    start_time = time.monotonic()
    success = False
    error: str | None = None
    pages: int | None = None
    unlocked = False
    source_bytes: int | None = None
    output_path: Path | None = None
    output_bytes: int | None = None
    verified = False
    original_result: str | None = None
    conversion_options = conversion_options or ConversionOptions(QUALITY_PRESETS["standard"], ("eng",))
    page_numbered = False

    try:
        source_path, source_stat, source_identity = inspect_pdf_input(source_path)
        source_bytes = source_stat.st_size
    except Exception as exc:
        error = str(exc)
        logging.error("Rejected PDF input '%s': %s", source_path, exc)
        duration = time.monotonic() - start_time
        logging.info(
            "Summary [FAIL] %s | pages=? | unlocked=no | verified=no | time=%.1fs",
            source_path.name,
            duration,
        )
        return ProcessResult(
            file=source_path.name,
            status="failed",
            pages=None,
            duration_s=duration,
            unlocked=False,
            original_action=original_action,
            quality_preset=conversion_options.preset.key,
            languages=conversion_options.languages,
            archival_output=conversion_options.preset.archival,
            error=error,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    # Source-controlled folders may be shared or attacker-writable. Keep the
    # stable input snapshot and unlock intermediates in the invoking user's
    # private OS temporary directory rather than beside the selected PDF.
    with tempfile.TemporaryDirectory(prefix="pdfconvertocr-") as tmp_dir:
        stem = safe_filename(source_path.stem)
        source_snapshot = Path(tmp_dir) / f"{stem}_source.pdf"
        unlocked_pdf = Path(tmp_dir) / f"{stem}_unlocked.pdf"
        ocr_staged_pdf = staging_pdf_path(output_dir, stem, "ocr")
        numbered_staged_pdf = staging_pdf_path(output_dir, stem, "numbered")

        work_file = source_snapshot
        try:
            copy_pdf_source_snapshot(source_path, source_snapshot, source_identity)
            os.utime(
                source_snapshot,
                ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
            )
            if is_pdf_locked(source_snapshot):
                unlock_pdf(str(source_snapshot), str(unlocked_pdf), tools)
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
                        _staged_path, _staged_stat, staged_identity = inspect_pdf_input(
                            staged_final_pdf
                        )
                        final_ok, final_error = validate_final_output(staged_final_pdf, pages, source_stat)
                        if not final_ok:
                            error = final_error or "Final output validation failed"
                        else:
                            assert_pdf_source_unchanged(
                                staged_final_pdf,
                                staged_identity,
                                "output publication",
                            )
                            assert_pdf_source_unchanged(
                                source_path, source_identity, "output publication"
                            )
                            verified = True
                            output_path = publish_staged_output(
                                staged_final_pdf,
                                output_dir,
                                stem,
                                staged_identity,
                            )
                            output_bytes = output_path.stat().st_size
                            logging.info(
                                "Verified output published: %s | text_pages=%s | bytes=%s",
                                output_path.name,
                                text_pages,
                                output_bytes,
                            )
                            try:
                                original_result = apply_original_action(
                                    source_path,
                                    archive_dir,
                                    original_action,
                                    source_identity,
                                    source_snapshot,
                                )
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
    try:
        assert_no_redirecting_reparse_path(config.source_dir)
    except UnsafePdfInputError as exc:
        logging.error("Unsafe batch source directory: %s", exc)
        return
    if not config.source_dir.is_dir():
        logging.error(f"Source directory not found: {config.source_dir!s}")
        return

    candidates = list(config.source_dir.glob("*.pdf"))
    pdfs: list[Path] = []
    for candidate in candidates:
        try:
            safe_path, _source_stat, _identity = inspect_pdf_input(candidate)
            pdfs.append(safe_path)
        except UnsafePdfInputError as exc:
            logging.warning("Skipping unsafe batch PDF '%s': %s", candidate, exc)

    if not pdfs:
        logging.info("No safe PDFs found - nothing to do.")
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
    try:
        ensure_runtime_dirs(config)
        configure_logging(config)
    except UnsafePdfInputError as exc:
        print(f"Unsafe runtime directory: {exc}", file=sys.stderr)
        return

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
            else:
                selected_path = lexical_absolute_path(p)
                logging.info(f"Single-file mode on: {selected_path!s}")
                process_single(
                    selected_path,
                    tools,
                    options.original_action,
                    conversion_options,
                )
    else:
        # No args → legacy batch mode
        process_batch(config, tools, options.original_action, conversion_options)

    logging.info("🏁 Finished")

if __name__ == "__main__":
    main()
