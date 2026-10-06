# PDFConvertOCR 6.2.1

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

PDFConvertOCR is a local Windows utility that turns scanned PDFs into searchable
PDFs. Its primary workflow adds **Convert to OCR (v6.2)** to the File Explorer
right-click menu. It can also process files from PowerShell or run a folder in
batch mode.

The application can rewrite a PDF that opens normally but has printing or
copying restrictions. It does not discover or recover an unknown PDF password.
Only process documents that you are authorized to modify.

## Quick install

For most users, install the packaged application:

PDFConvertOCR requires Windows 10 or 11.

1. Open the [PDFConvertOCR 6.2.1 release](https://github.com/jaywking/pdfconvertOCR/releases/tag/v6.2.1).
2. Download `PDFConvertOCR-Setup-v6.2.1.exe`.
3. Run the installer.
4. Right-click a PDF in File Explorer and choose **Convert to OCR (v6.2)**.

The installer runs per user under `%LOCALAPPDATA%\PDFConvertOCR`; it does not
require a separate Python, Ghostscript, Tesseract, or pngquant installation.
It verifies the approved bundled payload before installing or executing it.

The current installer is not Authenticode-signed, so Windows may identify its
publisher as unknown. Download it only from the official release above. The
SHA-256 of the 6.2.1 installer is:

```text
853f0c13067b767cd1a331efd31bc60b53677680c0a94f8aee6bd0cabf410f87
```

## Everyday use

PDFConvertOCR does not open as a separate desktop application. Start each
conversion from File Explorer:

1. Open the folder containing the PDF.
2. Right-click the PDF and select **Convert to OCR (v6.2)**.
3. Choose a quality preset and OCR language in the options window.
4. Select **Convert** and leave the conversion window open until it finishes.

Selecting **Cancel** or closing the options window stops before any files are
changed.

After a successful conversion, the searchable output is created next to the
source as `<name>_OCR.pdf`. The output keeps the source PDF's Modified Date.
Only after the output passes validation is the source moved into an
`Originals\` subfolder.

An existing output is never overwritten. If `Report_OCR.pdf` already exists,
the next output is `Report_OCR (1).pdf`, then `Report_OCR (2).pdf`, and so on.

For short coworker-facing instructions, see [HOW_TO_USE.txt](HOW_TO_USE.txt).

## Quality presets and OCR languages

| Preset | Behavior | Page numbers |
| --- | --- | --- |
| **Standard** | Deskews pages and creates a balanced searchable PDF. | Yes |
| **Straighten and rotate** | Standard processing plus automatic page-orientation correction. | Yes |
| **Small file** | Uses stronger JPEG compression for a smaller output. | Yes |
| **Archival PDF/A** | Creates OCRmyPDF-generated PDF/A output. PDFConvertOCR does not independently certify conformance. | No |

English is selected by default. The options window lists the language packs
reported by the active Tesseract runtime. The packaged installer includes
English and orientation data. Adding languages to the packaged application
requires rebuilding its verified Tesseract payload; source-checkout users may
use language packs installed in their approved Tesseract installation.

## Output and source-file safety

- OCR and page numbering are written to temporary staging files. The output is
  checked for readability, page count, OCR text, and the expected Modified Date
  before publication.
- If conversion or validation fails, the source and existing outputs remain in
  place.
- The default source action is **move**: after successful publication, the
  source is archived in `Originals\` using a timestamp and short unique ID.
  Command-line users can instead select **copy** or **keep**.
- A selected path must identify one ordinary PDF with one filesystem link.
  Symbolic links, junctions, redirecting reparse points, hard links, and NTFS
  alternate data stream paths are rejected.
- Processing reads a private snapshot of the verified source. The application
  checks source and staged-output identities again before publication and
  source-file handling.

Resource limits for unusually large or hostile PDFs remain planned. Until
measured limits are implemented, process unexpected documents individually
and avoid unattended oversized batches.

## Troubleshooting

### The right-click command is missing

Rerun the packaged installer. If the menu still does not appear, restart File
Explorer or sign out and back in. Source-checkout users can rerun
`install_right_click_context.bat`.

### Conversion fails or closes without producing an output

Review the newest log under `%LOCALAPPDATA%\PDFConvertOCR\logs` for a packaged
installation. A source checkout writes logs under its configured base directory.
The source is not moved unless a verified output was published.

### Packaged setup reports `ModuleNotFoundError: No module named 'fitz'`

Rerun the installer, or run `setup_installed_app.ps1` from
`%LOCALAPPDATA%\PDFConvertOCR`. Setup verifies the payload, replaces the local
Python runtime, reinstalls the complete hash-locked wheel set, and verifies the
required imports.

### Setup or build reports an integrity, digest, reparse-point, or signer error

Stop and obtain a fresh trusted installer or restore the reviewed build input.
Do not bypass the check or update `trusted-artifacts.json` merely to make an
unexpected local file pass.

### The PDF is rejected as linked, redirected, or changed

Use the original ordinary file rather than a shortcut, symbolic link, junction,
hard link, or NTFS alternate data stream. If another program is updating the
PDF, wait for it to finish or copy the completed PDF to a normal local filename
and retry.

### A PDF reader or AI tool still reports that no text can be extracted

Normal conversion skips OCR on pages that already claim to contain text. If
that existing text layer is unusable, a source-checkout user can create a
separate recovery copy by rasterizing and re-OCRing every page:

```powershell
& 'C:\LocalVenvs\pdfconvertOCR\Scripts\ocrmypdf.exe' --force-ocr --output-type pdf --no-overwrite 'input.pdf' 'fixed.pdf'
```

This is an advanced recovery step, not the normal application workflow.
`--force-ocr` rasterizes all page content, so vector content, interactive
features, or digital signatures may be lost, and file size or visual quality
may change. Verify the separate output carefully.

### Source checkout cannot find pngquant

OCRmyPDF requires the external `pngquant.exe` when PDFConvertOCR uses
optimization level 3. Install it with Chocolatey:

```powershell
choco install pngquant -y
```

### Source checkout reports a `pydantic-core` incompatibility

Repair the approved project environment with `bootstrap.ps1 -Recreate`. Global
or user-level Python packages are not supported runtime inputs.

## Source checkout setup

This section is for development or command-line use. Packaged-installer users
do not need these steps.

Requirements:

- Windows 10 or 11.
- The approved source/build Python recorded in `trusted-artifacts.json`
  (currently PSF Python 3.14.4 on this workstation).
- Ghostscript, Tesseract, and pngquant installed in their documented system
  locations.
- The project environment at `C:\LocalVenvs\pdfconvertOCR`.
- Python packages from the complete SHA-256-locked `requirements-lock.txt`.

Create the project environment or install its locked packages:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Utils\pdfconvertOCR\bootstrap.ps1'
```

Verify the approved source runtime and existing environment without installing
anything:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Utils\pdfconvertOCR\bootstrap.ps1' -VerifyOnly
```

If verification identifies a stale or damaged project environment, review the
error and recreate it explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Utils\pdfconvertOCR\bootstrap.ps1' -Recreate
```

Bootstrap does not fall back to `py.exe`, an arbitrary `python.exe`, or another
project's environment. It manages Python packages but does not install the
external Ghostscript, Tesseract, or pngquant tools.

To add the Explorer command from a source checkout, run
`install_right_click_context.bat`. Remove it with
`uninstall_right_click_context.bat`. Technical details are in
[RIGHT_CLICK_CONTEXT_MENU.md](RIGHT_CLICK_CONTEXT_MENU.md).

## Command-line use

Run the application with its explicit project interpreter:

```powershell
$pdfConvertPython = 'C:\LocalVenvs\pdfconvertOCR\Scripts\python.exe'

# Default: publish the output, then move the source into Originals
& $pdfConvertPython .\pdf_automation_v6.2.py 'C:\Docs\Report.pdf'

# Keep the source in place
& $pdfConvertPython .\pdf_automation_v6.2.py --original-action keep 'C:\Docs\Report.pdf'

# Copy the source into Originals and retain it in place
& $pdfConvertPython .\pdf_automation_v6.2.py --original-action copy 'C:\Docs\Report.pdf'
```

Valid source actions are `move`, `copy`, and `keep`.

Suppress the options window and provide conversion settings explicitly for
automation:

```powershell
& $pdfConvertPython .\pdf_automation_v6.2.py --no-options-prompt --quality-preset straighten-rotate --language eng 'C:\Docs\Scan.pdf'
& $pdfConvertPython .\pdf_automation_v6.2.py --no-options-prompt --quality-preset small-file --language eng 'C:\Docs\Scan.pdf'
& $pdfConvertPython .\pdf_automation_v6.2.py --no-options-prompt --quality-preset archival-pdfa --language eng 'C:\Docs\Archive.pdf'
```

Use a plus-separated value such as `--language eng+fra` only when every
requested language pack is installed.

### Batch mode

Running the script without PDF arguments processes every safe `*.pdf` in the
configured base directory. Set that directory explicitly before starting a
batch:

```powershell
$env:PDFCONVERTOCR_BASE_DIR = 'C:\Docs\Incoming'
& $pdfConvertPython .\pdf_automation_v6.2.py --no-options-prompt
$env:PDFCONVERTOCR_BASE_DIR = $null
```

Batch outputs go to `_complete\`, successfully handled sources go to
`_processed\`, and logs go to `logs\`. Batch mode is sequential and defaults to
Standard with English unless options are supplied.

## Building the Windows installer

The release build requires Inno Setup 6 and all approved inputs recorded in
`trusted-artifacts.json`.

Build a refreshed offline payload and compile the installer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
```

Verify the current tools and staged payload without refreshing or compiling:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 -VerifyOnly
```

Compile an already staged payload after performing the same integrity checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 -SkipVendorRefresh
```

The build writes both required release assets:

```text
dist\PDFConvertOCR-Setup-v6.2.1.exe
dist\ghostscript-10.07.0.tar.xz
```

Publish both files together. The Ghostscript source archive is downloaded from
the pinned Artifex URL and must match the SHA-256 in
`trusted-artifacts.json`.

The packaged runtime is Python 3.14.7. The build derives the CPython feature
and ABI wheel target from that version, removes prior staged vendor trees, and
installs only the complete hash-locked offline dependency set. Tcl/Tk is
included for the Explorer conversion-options window.

When intentionally changing a dependency, Python version, native runtime, or
build tool, independently verify its provenance, update the appropriate lock or
policy entry, rebuild the payload, and review the resulting diff. Never change
a digest solely to make an unexpected file pass.

## Security and integrity model

- Source bootstrap accepts only the approved signed CPython installation and
  project environment recorded in `trusted-artifacts.json`.
- Installer creation verifies source Python components, isolated build `pip`,
  the Inno Setup signer, the downloaded Python installer, and complete vendor
  inventories before compilation.
- Packaged setup verifies the same inventories before executing the Python
  installer or importing packages. There is no network or unpinned-package
  fallback during packaged setup.
- Runtime OCR accepts `ocrmypdf.exe` only from the packaged
  `python\Scripts` directory or `C:\LocalVenvs\pdfconvertOCR\Scripts` and
  rejects a trusted path containing a symlink or redirecting Windows reparse
  point.
- Packaged installs prepend their verified Ghostscript, Tesseract, and pngquant
  directories to `PATH`. Source checkouts use the documented system locations.

The 2026-10-05 security review reported four validated findings. Trusted
executable discovery, installer/build-input integrity, and link-backed-input
handling are remediated. Low-priority resource-exhaustion hardening is the only
remaining validated item and is tracked in [PARKING_LOT.md](PARKING_LOT.md).

## How it works

1. The application checks the selected source path and captures a stable file
   identity.
2. It copies the verified source through an open handle into a private temporary
   directory.
3. If the PDF opens but has printing or copying restrictions, Ghostscript
   creates an unrestricted working copy.
4. OCRmyPDF creates searchable output. Standard processing is equivalent to:

   ```text
   ocrmypdf.exe -l eng --skip-text --optimize 3 --jpeg-quality 40 --output-type pdf --deskew input.pdf output.pdf
   ```

5. Applicable presets add `Page X of Y` with PyMuPDF. Archival PDF/A intentionally
   skips this modification.
6. The application restores the source Modified Date, validates the staged
   output, rechecks file identities, and publishes without overwriting.
7. Only then does it apply the requested move, copy, or keep action to the
   source.

## Important project files

- `app_metadata.json` — application version and Explorer integration metadata.
- `pdf_automation_v6.2.py` — conversion, validation, and file-handling logic.
- `run_single_pdf.bat` — packaged/source Explorer launcher.
- `bootstrap.ps1` — approved source-environment setup and verification.
- `requirements.txt` and `requirements-lock.txt` — dependency entry point and
  complete hash-locked Windows CPython 3.14 dependency set.
- `trusted-artifacts.json` and `trusted_artifacts.ps1` — approved versions,
  hashes, inventories, and verification functions.
- `setup_installed_app.ps1` — packaged payload verification and runtime setup.
- `installer\` — Inno Setup release build files.
- `HOW_TO_USE.txt` — short instructions installed with the application.
- `RIGHT_CLICK_CONTEXT_MENU.md` — Explorer integration and repair details.
- `PARKING_LOT.md` — evaluated future work and the remaining security follow-up.
- `archives\` — inactive historical scripts and documentation.

## License

Copyright (C) 2025-2026 Jay King.

PDFConvertOCR's original source code is licensed under the
[GNU Affero General Public License version 3](LICENSE), with no later-version
option (`AGPL-3.0-only`). You may use, study, modify, and redistribute it under
that license's terms, including its source-availability requirements.

Third-party components retain their own licenses. Release installers bundle
Python, PyMuPDF, OCRmyPDF and its Python dependencies, Ghostscript, Tesseract,
and pngquant. Review `THIRD_PARTY_NOTICES.txt` in an installed application and
the bundled component license material before redistribution. PyMuPDF and
Ghostscript are offered under AGPL or separate commercial licensing; this
project uses their open-source distributions and does not grant a commercial
license to them.

The packaged Ghostscript runtime is version 10.07.0. Its AGPL text is installed
at `vendor\ghostscript\doc\COPYING`. The matching source archive is
[`ghostscript-10.07.0.tar.xz`](https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10070/ghostscript-10.07.0.tar.xz).

- SHA-256: `ddace4e1721f967a55039baff564840225e0baa1d4f5432247ca1ccd1473b7c1`
- SHA-512: `1c2a14951223c975a53bd9767c28bd3a6e420c385a5e0d7a60a5ff5b091bc027929c815bf57cddf97611e8d265ece1c219321737f2cabb5646685c6e8cdb85c9`

Every release that bundles this Ghostscript runtime must also publish that
corresponding source archive.
