"""Generated-fixture release smoke test for the real PDFConvertOCR pipeline.

Run this script with the Python interpreter belonging to the runtime under test.
It intentionally uses only non-sensitive, temporary fixtures.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pdf_automation_v6.2.py"
SPEC = importlib.util.spec_from_file_location("pdfconvertocr_release_smoke", MODULE_PATH)
app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app
SPEC.loader.exec_module(app)


def checked_output(command: list[str]) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def scan_image(path: Path, lines: list[str], rotation: int = 0, jpeg2000: bool = False) -> None:
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    font = ImageFont.truetype(str(font_path), 42) if font_path.is_file() else ImageFont.load_default()
    y = 120
    for line in lines:
        draw.text((100, y), line, fill="black", font=font)
        y += 90
    if rotation:
        image = image.rotate(rotation, expand=True, fillcolor="white")
    image.save(path, format="JPEG2000" if jpeg2000 else "PNG")


def image_pdf(path: Path, images: list[Path]) -> None:
    with fitz.open() as document:
        for image_path in images:
            page = document.new_page(width=612, height=792)
            page.insert_image(page.rect, filename=str(image_path))
        document.set_metadata({"producer": "PDFConvertOCR release smoke"})
        document.save(path)


def restricted_pdf(source: Path, destination: Path) -> None:
    with fitz.open(source) as document:
        document.save(
            destination,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="release-smoke-owner",
            user_pw="",
            permissions=0,
        )


def existing_text_pdf(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), "Existing searchable release text", fontsize=18)
        document.save(path)


def assert_output(result: app.ProcessResult, expected_pages: int, source_mtime_ns: int) -> Path:
    if result.status != "ok" or not result.verified or not result.output_path:
        raise AssertionError(f"Conversion failed: {result}")
    output = Path(result.output_path)
    if output.stat().st_mtime_ns != source_mtime_ns:
        raise AssertionError(f"Modified date changed: {output}")
    with fitz.open(output) as document:
        if len(document) != expected_pages:
            raise AssertionError(f"Unexpected page count in {output}: {len(document)}")
        if not all(page.get_text("text").strip() for page in document):
            raise AssertionError(f"Searchable text is missing in {output}")
        if document.metadata.get("title") == "Untitled":
            raise AssertionError(f"Ghostscript/OCRmyPDF injected the title 'Untitled': {output}")
    return output


def copy_fixture(source: Path, destination: Path) -> Path:
    shutil.copy2(source, destination)
    return destination


def run(args: argparse.Namespace) -> dict[str, object]:
    ocrmypdf = Path(sys.executable).with_name("ocrmypdf.exe")
    if not ocrmypdf.is_file():
        ocrmypdf = Path(sys.executable).parent / "Scripts" / "ocrmypdf.exe"
    tools = app.RuntimeTools(str(args.ghostscript), str(ocrmypdf), str(args.tesseract), str(args.pngquant))
    for executable in (Path(tools.ghostscript), Path(tools.ocrmypdf), Path(tools.tesseract), Path(tools.pngquant)):
        if not executable.is_file():
            raise FileNotFoundError(executable)

    versions = {
        "ghostscript": checked_output([tools.ghostscript, "--version"]),
        "ocrmypdf": checked_output([tools.ocrmypdf, "--version"]),
    }
    if versions != {"ghostscript": "10.08.0", "ocrmypdf": "17.13.0"}:
        raise AssertionError(f"Unexpected tool versions: {versions}")

    path_parts = [
        str(Path(tools.ghostscript).parent),
        str(Path(tools.tesseract).parent),
        str(Path(tools.pngquant).parent),
    ]
    app.os.environ["PATH"] = app.os.pathsep.join(path_parts + [app.os.environ.get("PATH", "")])

    with tempfile.TemporaryDirectory(prefix="pdfconvertocr-release-") as temporary:
        work = Path(temporary)
        output = work / "output"
        originals = work / "Originals"
        output.mkdir()

        first_image = work / "scan-1.png"
        second_image = work / "scan-2.png"
        rotated_image = work / "rotated.png"
        jpx_image = work / "benign.jp2"
        common_lines = [
            "PDFConvertOCR security release validation",
            "English text and multilingual sample: cafe resume jalapeno",
            "Generated fixture with no sensitive information",
        ] * 3
        scan_image(first_image, common_lines)
        scan_image(second_image, ["Second page searchable text"] * 8)
        scan_image(
            rotated_image,
            [
                "Rotated page orientation validation",
                "This generated document contains several full sentences.",
                "The quick brown fox jumps over the lazy dog.",
                "Release testing confirms automatic orientation correction.",
                "Every line uses ordinary English words for recognition.",
                "Searchable output must preserve the original page count.",
                "No private or production information appears in this fixture.",
                "Ghostscript and OCRmyPDF run through their normal workflow.",
                "The final document is checked for extracted text.",
                "This paragraph completes the rotation sample.",
            ],
            rotation=180,
        )
        scan_image(jpx_image, ["Benign JPEG 2000 validation"] * 8, jpeg2000=True)

        multipage = work / "multipage.pdf"
        rotated = work / "rotated.pdf"
        jpx = work / "jpeg2000.pdf"
        existing = work / "existing-text.pdf"
        locked = work / "restricted.pdf"
        image_pdf(multipage, [first_image, second_image])
        image_pdf(rotated, [rotated_image])
        image_pdf(jpx, [jpx_image])
        existing_text_pdf(existing)
        restricted_pdf(multipage, locked)

        cases = [
            ("standard", multipage, "keep", 2),
            ("straighten-rotate", rotated, "copy", 1),
            ("small-file", jpx, "move", 1),
            ("archival-pdfa", multipage, "keep", 2),
            ("standard", locked, "keep", 2),
            ("standard", existing, "keep", 1),
        ]
        results: list[app.ProcessResult] = []
        outputs: list[Path] = []
        for index, (preset, fixture, action, pages) in enumerate(cases, 1):
            source = copy_fixture(fixture, work / f"case-{index}-{fixture.name}")
            source_mtime = source.stat().st_mtime_ns
            result = app._process_one_pdf(
                source,
                output,
                originals,
                work,
                tools,
                action,
                app.ConversionOptions(app.QUALITY_PRESETS[preset], ("eng",)),
            )
            results.append(result)
            outputs.append(assert_output(result, pages, source_mtime))
            if action == "move" and source.exists():
                raise AssertionError("Move action left the source in place")
            if action in {"copy", "keep"} and not source.exists():
                raise AssertionError(f"{action} action removed the source")
            if action == "copy" and not any(originals.glob(f"{source.stem}_*.pdf")):
                raise AssertionError("Copy action did not archive a copy")

        duplicate_dir = work / "duplicate"
        duplicate_dir.mkdir()
        duplicate_source = copy_fixture(multipage, duplicate_dir / "case-1-multipage.pdf")
        duplicate_result = app._process_one_pdf(
            duplicate_source,
            output,
            originals,
            work,
            tools,
            "keep",
            app.ConversionOptions(app.QUALITY_PRESETS["standard"], ("eng",)),
        )
        duplicate_output = assert_output(duplicate_result, 2, duplicate_source.stat().st_mtime_ns)
        if duplicate_output.name == outputs[0].name or "(1)" not in duplicate_output.stem:
            raise AssertionError(f"Duplicate output was not uniquely named: {duplicate_output.name}")

        if not results[4].unlocked:
            raise AssertionError("Restricted fixture did not invoke the Ghostscript unlock path")

        return {
            "versions": versions,
            "conversions": len(results) + 1,
            "presets": sorted({result.quality_preset for result in results}),
            "restricted_unlocked": results[4].unlocked,
            "output_names": [item.name for item in [*outputs, duplicate_output]],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ghostscript", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--pngquant", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
