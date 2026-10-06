import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf as fitz


MODULE_PATH = Path(__file__).resolve().parents[1] / "pdf_automation_v6.2.py"
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
        self.original_publish = app.publish_staged_output
        self.original_validate_final = app.validate_final_output
        self.original_unique_archive = app.unique_archive_path
        self.original_next_output = app.next_output_path
        app.is_pdf_locked = lambda _path: False

    def tearDown(self) -> None:
        app.ocr_pdf = self.original_ocr
        app.is_pdf_locked = self.original_locked
        app.apply_original_action = self.original_action
        app.add_page_numbers = self.original_page_numbers
        app.publish_staged_output = self.original_publish
        app.validate_final_output = self.original_validate_final
        app.unique_archive_path = self.original_unique_archive
        app.next_output_path = self.original_next_output
        self.tmp.cleanup()

    def fake_ocr(self, source: str, destination: str, _tools, _options) -> tuple[bool, str | None]:
        shutil.copy2(source, destination)
        return True, None

    def test_trusted_ocrmypdf_rejects_path_and_other_user_decoys(self) -> None:
        app_dir = self.root / "app"
        decoy = self.root / "other-user" / "ocrmypdf.exe"
        decoy.parent.mkdir(parents=True)
        decoy.touch()
        config = app.AppConfig(app_dir, app_dir, app_dir, app_dir, app_dir, app_dir)

        with mock.patch.object(app.shutil, "which", return_value=str(decoy)), mock.patch.object(
            app, "trusted_ocrmypdf_roots", return_value=(app_dir / "python",)
        ):
            self.assertEqual(app.find_trusted_ocrmypdf(config), "")

    def test_trusted_ocrmypdf_accepts_packaged_runtime(self) -> None:
        app_dir = self.root / "app"
        wrapper = app_dir / "python" / "Scripts" / "ocrmypdf.exe"
        wrapper.parent.mkdir(parents=True)
        wrapper.touch()
        config = app.AppConfig(app_dir, app_dir, app_dir, app_dir, app_dir, app_dir)

        self.assertEqual(app.find_trusted_ocrmypdf(config), str(wrapper.resolve()))

    def test_trusted_ocrmypdf_rejects_linked_runtime_root(self) -> None:
        app_dir = self.root / "app"
        runtime_root = app_dir / "python"
        wrapper = runtime_root / "Scripts" / "ocrmypdf.exe"
        wrapper.parent.mkdir(parents=True)
        wrapper.touch()
        config = app.AppConfig(app_dir, app_dir, app_dir, app_dir, app_dir, app_dir)

        with mock.patch.object(
            app, "trusted_ocrmypdf_roots", return_value=(runtime_root,)
        ), mock.patch.object(
            app, "path_contains_reparse_point", side_effect=lambda path: path == runtime_root
        ):
            self.assertEqual(app.find_trusted_ocrmypdf(config), "")

    def test_trusted_ocrmypdf_rejects_symlink_escape(self) -> None:
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlinks are unavailable")
        app_dir = self.root / "app"
        outside = self.root / "outside.exe"
        outside.touch()
        wrapper = app_dir / "python" / "Scripts" / "ocrmypdf.exe"
        wrapper.parent.mkdir(parents=True)
        try:
            wrapper.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks are unavailable: {exc}")
        config = app.AppConfig(app_dir, app_dir, app_dir, app_dir, app_dir, app_dir)

        with mock.patch.object(app, "trusted_ocrmypdf_roots", return_value=(app_dir / "python",)):
            self.assertEqual(app.find_trusted_ocrmypdf(config), "")

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

    def make_junction(self, link: Path, target: Path) -> None:
        if os.name != "nt":
            self.skipTest("Windows directory junctions are required")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            self.skipTest(f"Could not create a Windows junction: {result.stderr}")

    def test_hard_linked_input_is_rejected_before_processing(self) -> None:
        target = self.root / "Private.pdf"
        selected = self.root / "Selected.pdf"
        make_pdf(target, "Private target text")
        os.link(target, selected)

        result = self.process(selected, "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("exactly one hard link", result.error)
        self.assertTrue(target.exists())
        self.assertTrue(selected.exists())
        self.assertFalse(list(self.root.glob("Selected_OCR*.pdf")))
        self.assertFalse((self.root / "Originals").exists())

    def test_parent_junction_input_is_rejected_without_moving_target(self) -> None:
        target_dir = self.root / "target"
        target_dir.mkdir()
        target = target_dir / "Target.pdf"
        make_pdf(target, "Junction target")
        junction = self.root / "linked-folder"
        self.make_junction(junction, target_dir)
        try:
            result = self.process(junction / "Target.pdf", "move")

            self.assertEqual(result.status, "failed")
            self.assertIn("reparse point", result.error)
            self.assertTrue(target.exists())
            self.assertFalse(list(target_dir.glob("Target_OCR*.pdf")))
            self.assertFalse((target_dir / "Originals").exists())
        finally:
            if junction.exists():
                os.rmdir(junction)

    def test_batch_root_junction_is_rejected_before_discovery(self) -> None:
        target_dir = self.root / "batch-target"
        target_dir.mkdir()
        make_pdf(target_dir / "Target.pdf")
        junction = self.root / "batch-root"
        self.make_junction(junction, target_dir)
        config = app.AppConfig(
            self.root,
            junction,
            junction,
            junction / "_processed",
            junction / "_complete",
            junction / "logs",
        )
        try:
            app.process_batch(
                config,
                self.tools,
                "move",
                app.ConversionOptions(app.QUALITY_PRESETS["standard"], ("eng",)),
            )

            self.assertTrue((target_dir / "Target.pdf").exists())
            self.assertFalse((target_dir / "_complete").exists())
            self.assertFalse((target_dir / "_processed").exists())
        finally:
            if junction.exists():
                os.rmdir(junction)

    def test_batch_ignores_hard_linked_pdf_entry(self) -> None:
        target = self.root / "private-target.bin"
        selected = self.root / "Selected.pdf"
        make_pdf(target, "Batch hard-link target")
        os.link(target, selected)
        config = app.AppConfig(
            self.root,
            self.root,
            self.root,
            self.root / "_processed",
            self.root / "_complete",
            self.root / "logs",
        )

        app.process_batch(
            config,
            self.tools,
            "move",
            app.ConversionOptions(app.QUALITY_PRESETS["standard"], ("eng",)),
        )

        self.assertTrue(target.exists())
        self.assertTrue(selected.exists())
        self.assertFalse((self.root / "_complete").exists())
        self.assertFalse((self.root / "_processed").exists())

    def test_ntfs_alternate_data_stream_input_is_rejected(self) -> None:
        if os.name != "nt":
            self.skipTest("NTFS alternate data streams are Windows-specific")
        result = self.process(self.root / "Carrier.pdf:Hidden.pdf", "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("alternate data stream", result.error)

    def test_source_replacement_after_validation_blocks_publication(self) -> None:
        source = self.root / "ReplaceBeforePublish.pdf"
        replacement = self.root / "Replacement.pdf"
        make_pdf(source, "Original identity")
        make_pdf(replacement, "Replacement identity")

        def replace_after_validation(final_pdf, expected_pages, source_stat):
            result = self.original_validate_final(final_pdf, expected_pages, source_stat)
            os.replace(replacement, source)
            return result

        app.validate_final_output = replace_after_validation
        result = self.process(source, "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("changed before output publication", result.error)
        self.assertTrue(source.exists())
        self.assertFalse(list(self.root.glob("ReplaceBeforePublish_OCR*.pdf")))
        self.assertFalse((self.root / "Originals").exists())

    def test_in_place_source_mutation_blocks_publication(self) -> None:
        source = self.root / "MutatedBeforePublish.pdf"
        replacement = self.root / "Replacement.pdf"
        make_pdf(source, "Original identity")
        make_pdf(replacement, "Replacement identity with a different size")

        def mutate_after_validation(final_pdf, expected_pages, source_stat):
            result = self.original_validate_final(final_pdf, expected_pages, source_stat)
            source.write_bytes(replacement.read_bytes())
            return result

        app.validate_final_output = mutate_after_validation
        result = self.process(source, "move")

        self.assertEqual(result.status, "failed")
        self.assertIn("changed before output publication", result.error)
        self.assertTrue(source.exists())
        self.assertFalse(list(self.root.glob("MutatedBeforePublish_OCR*.pdf")))
        self.assertFalse((self.root / "Originals").exists())

    def test_source_replacement_after_publication_is_not_moved(self) -> None:
        source = self.root / "ReplaceBeforeMove.pdf"
        replacement = self.root / "Replacement.pdf"
        make_pdf(source, "Original identity")
        make_pdf(replacement, "Replacement identity")

        def replace_after_publication(staged_path, output_dir, stem, expected_identity):
            published = self.original_publish(
                staged_path, output_dir, stem, expected_identity
            )
            os.replace(replacement, source)
            return published

        app.publish_staged_output = replace_after_publication
        result = self.process(source, "move")

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.verified)
        self.assertIn("changed before the original-file move", result.error)
        self.assertTrue(source.exists())
        self.assertTrue(Path(result.output_path).exists())
        self.assertFalse(list((self.root / "Originals").glob("*.pdf")))

    def test_original_action_rechecks_after_archive_path_creation(self) -> None:
        for action in ("copy", "move"):
            with self.subTest(action=action):
                case_dir = self.root / action
                case_dir.mkdir()
                source = case_dir / "Source.pdf"
                replacement = case_dir / "Replacement.pdf"
                stable_source = case_dir / "Stable.pdf"
                make_pdf(source, "Original identity")
                make_pdf(replacement, "Replacement identity")
                shutil.copy2(source, stable_source)
                _path, _source_stat, identity = app.inspect_pdf_input(source)

                def replace_during_destination_creation(src, archive_dir):
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    os.replace(replacement, src)
                    return archive_dir / "archive.pdf"

                app.unique_archive_path = replace_during_destination_creation
                with self.assertRaises(app.UnsafePdfInputError):
                    app.apply_original_action(
                        source,
                        case_dir / "Originals",
                        action,
                        identity,
                        stable_source,
                    )

                self.assertTrue(source.exists())
                self.assertFalse((case_dir / "Originals" / "archive.pdf").exists())
                app.unique_archive_path = self.original_unique_archive

    def test_staged_output_replacement_during_publication_is_rejected(self) -> None:
        staged = self.root / ".Report.numbered.test.pdf"
        attacker = self.root / "Attacker.pdf"
        make_pdf(staged, "Validated output")
        make_pdf(attacker, "Unvalidated replacement")
        _path, _source_stat, identity = app.inspect_pdf_input(staged)

        def replace_before_link(output_dir, stem):
            os.replace(attacker, staged)
            return self.original_next_output(output_dir, stem)

        app.next_output_path = replace_before_link
        with self.assertRaises(app.UnsafePdfInputError):
            app.publish_staged_output(staged, self.root, "Report", identity)

        self.assertFalse((self.root / "Report_OCR.pdf").exists())

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
