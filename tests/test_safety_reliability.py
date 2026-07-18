import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz


MODULE_PATH = Path(__file__).resolve().parents[1] / "pdf_automation_v6.1.py"
SPEC = importlib.util.spec_from_file_location("pdf_automation_v6_1", MODULE_PATH)
app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app
SPEC.loader.exec_module(app)


def make_pdf(path: Path, text: str = "Safety test text") -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
        doc.save(path)


class SafetyReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tools = app.RuntimeTools("gs", "ocr", "tesseract", "pngquant")
        self.original_ocr = app.ocr_pdf
        self.original_locked = app.is_pdf_locked
        self.original_action = app.apply_original_action
        self.original_page_numbers = app.add_page_numbers
        app.is_pdf_locked = lambda _path: False

    def tearDown(self) -> None:
        app.ocr_pdf = self.original_ocr
        app.is_pdf_locked = self.original_locked
        app.apply_original_action = self.original_action
        app.add_page_numbers = self.original_page_numbers
        self.tmp.cleanup()

    def fake_ocr(self, source: str, destination: str, _tools, _options) -> tuple[bool, str | None]:
        shutil.copy2(source, destination)
        return True, None

    def process(self, source: Path, action: str = "keep"):
        app.ocr_pdf = self.fake_ocr
        return app._process_one_pdf(
            source,
            self.root,
            self.root / "Originals",
            self.root,
            self.tools,
            action,
        )

    def test_next_output_path_uses_numbered_siblings(self) -> None:
        (self.root / "Report_OCR.pdf").touch()
        (self.root / "Report_OCR (1).pdf").touch()
        self.assertEqual(app.next_output_path(self.root, "Report").name, "Report_OCR (2).pdf")

    def test_page_numbering_writes_separate_file(self) -> None:
        source = self.root / "source.pdf"
        numbered = self.root / "numbered.pdf"
        make_pdf(source)
        original_bytes = source.read_bytes()
        self.assertTrue(app.add_page_numbers(source, numbered))
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertTrue(numbered.exists())

    def test_keep_publishes_verified_unique_output_without_touching_source(self) -> None:
        source = self.root / "Report.pdf"
        make_pdf(source)
        existing = self.root / "Report_OCR.pdf"
        existing.write_bytes(b"existing output")

        result = self.process(source, "keep")

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.verified)
        self.assertTrue(source.exists())
        self.assertEqual(existing.read_bytes(), b"existing output")
        self.assertEqual(Path(result.output_path).name, "Report_OCR (1).pdf")
        self.assertGreater(result.output_bytes, 0)

    def test_copy_archives_original_without_removing_source(self) -> None:
        source = self.root / "CopyMe.pdf"
        make_pdf(source)

        result = self.process(source, "copy")

        self.assertEqual(result.status, "ok")
        self.assertTrue(source.exists())
        archived = list((self.root / "Originals").glob("*.pdf"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), source.read_bytes())

    def test_move_archives_original_after_verified_publish(self) -> None:
        source = self.root / "MoveMe.pdf"
        make_pdf(source)

        result = self.process(source, "move")

        self.assertEqual(result.status, "ok")
        self.assertFalse(source.exists())
        self.assertTrue(Path(result.output_path).exists())
        self.assertEqual(len(list((self.root / "Originals").glob("*.pdf"))), 1)

    def test_missing_ocr_text_keeps_source_and_removes_staging_files(self) -> None:
        source = self.root / "NoText.pdf"
        make_pdf(source, "Expected OCR text")

        def blank_ocr(_source: str, destination: str, _tools, _options) -> tuple[bool, str | None]:
            make_pdf(Path(destination), "")
            return True, None

        app.ocr_pdf = blank_ocr
        result = app._process_one_pdf(source, self.root, self.root / "Originals", self.root, self.tools, "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("OCR text missing", result.error)
        self.assertTrue(source.exists())
        self.assertFalse(list(self.root.glob(".*.pdf")))
        self.assertFalse(list((self.root / "Originals").glob("*.pdf")) if (self.root / "Originals").exists() else [])

    def test_mismatched_ocr_page_count_keeps_source_and_existing_outputs(self) -> None:
        source = self.root / "Mismatch.pdf"
        make_pdf(source)
        existing = self.root / "Mismatch_OCR.pdf"
        existing.write_bytes(b"existing output")

        def mismatched_ocr(_source: str, destination: str, _tools, _options) -> tuple[bool, str | None]:
            with fitz.open() as doc:
                for text in ("First page", "Unexpected second page"):
                    page = doc.new_page()
                    page.insert_text((72, 72), text)
                doc.save(destination)
            return True, None

        app.ocr_pdf = mismatched_ocr
        result = app._process_one_pdf(source, self.root, self.root / "Originals", self.root, self.tools, "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("page count", result.error)
        self.assertTrue(source.exists())
        self.assertEqual(existing.read_bytes(), b"existing output")

    def test_page_numbering_failure_keeps_source_and_removes_staging_files(self) -> None:
        source = self.root / "PageNumbers.pdf"
        make_pdf(source)
        app.ocr_pdf = self.fake_ocr
        app.add_page_numbers = lambda _source, _destination: False

        result = app._process_one_pdf(source, self.root, self.root / "Originals", self.root, self.tools, "move")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "Page numbering failed")
        self.assertTrue(source.exists())
        self.assertFalse(list(self.root.glob(".*.pdf")))

    def test_unreadable_output_fails_final_validation(self) -> None:
        invalid = self.root / "invalid.pdf"
        invalid.write_bytes(b"not a PDF")
        source = self.root / "source.pdf"
        make_pdf(source)

        valid, error = app.validate_final_output(invalid, 1, source.stat())

        self.assertFalse(valid)
        self.assertIn("Could not validate final output", error)

    def test_original_action_failure_keeps_source_and_reports_published_output(self) -> None:
        source = self.root / "ArchiveFailure.pdf"
        make_pdf(source)

        def fail_original_action(*_args, **_kwargs):
            raise OSError("archive unavailable")

        app.apply_original_action = fail_original_action
        result = self.process(source, "move")

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.verified)
        self.assertTrue(source.exists())
        self.assertTrue(Path(result.output_path).exists())
        self.assertIn("original action failed", result.error)


if __name__ == "__main__":
    unittest.main()
