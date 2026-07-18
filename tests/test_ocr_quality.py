import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "pdf_automation_v6.1.py"
SPEC = importlib.util.spec_from_file_location("pdf_automation_v6_1_quality", MODULE_PATH)
app = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app
SPEC.loader.exec_module(app)


TOOLS = app.RuntimeTools("gs", "ocrmypdf", "tesseract", "pngquant")


class OcrQualityTests(unittest.TestCase):
    def options(self, preset: str, languages=("eng",)):
        return app.ConversionOptions(app.QUALITY_PRESETS[preset], languages)

    def test_parses_installed_languages_and_excludes_orientation_data(self):
        output = 'List of available languages in "C:\\tessdata" (3):\neng\nfra\nosd\n'
        self.assertEqual(app.parse_tesseract_languages(output), ("eng", "fra"))

    def test_rejects_unavailable_language(self):
        with self.assertRaisesRegex(ValueError, "fra"):
            app.normalize_languages("eng+fra", ("eng",))

    def test_builds_expected_preset_commands_without_cleaning_flags(self):
        expectations = {
            "standard": ["--jpeg-quality", "40", "--output-type", "pdf", "--deskew"],
            "straighten-rotate": ["--jpeg-quality", "40", "--output-type", "pdf", "--deskew", "--rotate-pages"],
            "archival-pdfa": ["--jpeg-quality", "40", "--output-type", "pdfa", "--deskew"],
            "small-file": ["--jpeg-quality", "25", "--output-type", "pdf", "--deskew"],
        }
        forbidden = {"--clean", "--clean-final", "--remove-background", "--tesseract-downsample-large-images"}
        for preset, expected_flags in expectations.items():
            with self.subTest(preset=preset):
                command = app.build_ocr_command("input.pdf", "output.pdf", TOOLS, self.options(preset, ("eng", "fra")))
                self.assertEqual(command[:3], ["ocrmypdf", "-l", "eng+fra"])
                for flag in expected_flags:
                    self.assertIn(flag, command)
                self.assertTrue(forbidden.isdisjoint(command))

    def test_archival_preset_omits_page_numbers(self):
        self.assertFalse(self.options("archival-pdfa").preset.add_page_numbers)
        for preset in ("standard", "straighten-rotate", "small-file"):
            self.assertTrue(self.options(preset).preset.add_page_numbers)

    def test_cli_resolution_is_noninteractive_when_requested(self):
        with patch.object(app, "discover_tesseract_languages", return_value=("eng", "fra")), patch.object(app, "prompt_conversion_options") as prompt:
            options = app.resolve_conversion_options(TOOLS, "small-file", "eng+fra", show_prompt=False)
        self.assertEqual(options.preset.key, "small-file")
        self.assertEqual(options.languages, ("eng", "fra"))
        prompt.assert_not_called()

    def test_cancelled_prompt_returns_none_before_processing(self):
        with patch.object(app, "discover_tesseract_languages", return_value=("eng",)), patch.object(app, "prompt_conversion_options", return_value=None):
            options = app.resolve_conversion_options(TOOLS, None, None, show_prompt=True)
        self.assertIsNone(options)


if __name__ == "__main__":
    unittest.main()
