# Right-Click Context Menu Implementation

This project implements the Explorer right-click action with these pieces:

1. A Windows Registry shell verb for `.pdf` files.
2. A batch wrapper that receives the selected PDF path from Explorer.
3. The Python script's single-file mode and conversion-options prompt.
4. Runtime tools available either globally or from the packaged install's `vendor\` folder.

## Files involved

- `registry/add_OCR_context_v6.2.reg` adds the Explorer menu item.
- `app_metadata.json` is the source of truth for the app version, menu label, registry verb, runner script, and main script names used by the install/build scripts.
- `install_right_click_context.bat` is the double-click installer for the Explorer menu item.
- `install_right_click_context.ps1` bootstraps the project and writes the user-level registry keys.
- `uninstall_right_click_context.bat` removes the Explorer menu item.
- `run_single_pdf.bat` is the command Explorer runs.
- `bootstrap.ps1` creates the centralized virtual environment from the approved signed source Python and reinstalls the complete hash-locked dependency set. It fails closed when an existing environment does not match policy; `-Recreate` is the explicit replacement path.
- `pdf_automation_v6.2.py` processes the selected PDF when given a PDF path argument.
- `requirements-lock.txt` pins and hashes the complete supported Python dependency graph.
- `trusted-artifacts.json` records approved runtime versions, source locations, SHA-256 values, directory-tree digests, and signer requirements.
- `trusted_artifacts.ps1` provides the shared artifact, reparse-point, and Authenticode checks.
- `setup_installed_app.ps1` verifies the bundled manifests and payloads, replaces the packaged Python runtime, and installs the exact offline hash-locked wheel set.
- `installer/PDFConvertOCR.iss` creates the per-user Windows installer.

## Packaged installer

For non-technical users, the preferred path is the Inno Setup installer:

```text
PDFConvertOCR-Setup-v6.2.1.exe
```

That installer copies the app to:

```text
%LOCALAPPDATA%\PDFConvertOCR
```

It also writes the current-user PDF shell verb and points it at the installed `run_single_pdf.bat`.

The packaged install bundles runtime dependencies under the install folder:

- `python\`: local Python runtime
- `vendor\ghostscript\`: Ghostscript runtime
- `vendor\tesseract\`: Tesseract runtime and tessdata
- `vendor\pngquant\`: pngquant executable

On install or upgrade, Inno Setup removes every old staged vendor runtime tree
before copying the new payload. `setup_installed_app.ps1` then rejects any
changed, missing, extra, or reparse-point-backed bundled file before it runs the Python
installer. A repair always replaces the installed local Python runtime from the
verified offline media and installs only the hash-locked wheel set.

The installed tool is intentionally used from Explorer, not from a standalone app window. After installation, users should:

1. Open the folder containing their PDF.
2. Right-click the PDF.
3. Choose **Convert to OCR (v6.2)**, select a quality preset and installed OCR
   language in the prompt, then start conversion.

The installer includes `HOW_TO_USE.txt` and a Start Menu shortcut named **How to use PDFConvertOCR** for these short instructions.

## Source-checkout double-click installer

When running from a source checkout, the easiest way to install the right-click action is to double-click:

```text
install_right_click_context.bat
```

That batch file runs `install_right_click_context.ps1` with `-ExecutionPolicy Bypass`. The PowerShell installer:

1. Confirms the expected project files exist.
2. Runs `bootstrap.ps1` to create `C:\LocalVenvs\pdfconvertOCR` when needed,
   verify the approved runtime, and install the locked dependencies. An
   unapproved existing environment stops setup until it is explicitly recreated.
3. Creates the Explorer PDF shell verb under the current user's registry hive.
4. Points that shell verb at this repo's `run_single_pdf.bat`.

The installer uses this user-level registry path:

```text
HKCU\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2
```

Using `HKCU` keeps the install scoped to the current Windows user and usually avoids needing an elevated terminal. The source-checkout installer still expects dependencies to be installed globally or available through `bootstrap.ps1`.

`bootstrap.ps1` accepts only the source Python and project-environment identity
recorded in `trusted-artifacts.json`; it does not fall back to another Python on
PATH. Use `bootstrap.ps1 -VerifyOnly` for a non-installing check and
`bootstrap.ps1 -Recreate` only after reviewing a reported mismatch.

## Manual registry verb

The older/manual install path is to import `registry/add_OCR_context_v6.2.reg`:

```reg
Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2]
@="Convert to OCR (v6.2)"
"Icon"="C:\\Windows\\System32\\imageres.dll,-5302"
"MultiSelectModel"="Document"

[HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2\command]
@="\"C:\\Utils\\pdfconvertOCR\\run_single_pdf.bat\" \"%L\""
```

What each part does:

- `HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2` registers a shell command for PDF files.
- The default value, `Convert to OCR (v6.2)`, is the label shown in Explorer.
- `Icon` chooses the icon shown next to the menu item.
- `MultiSelectModel=Document` allows the command to appear when multiple PDF documents are selected.
- The `command` default value is the executable command Explorer runs.
- `%L` is replaced by Explorer with the selected PDF's long file path. It is quoted so paths with spaces work.

## Command flow

When a user selects a PDF and chooses `Convert to OCR (v6.2)`, Explorer runs:

```bat
"C:\Utils\pdfconvertOCR\run_single_pdf.bat" "C:\path\to\selected.pdf"
```

`run_single_pdf.bat` then:

1. Sets the project root from the batch file location.
2. Looks for `C:\LocalVenvs\pdfconvertOCR\Scripts\python.exe`.
3. Runs `bootstrap.ps1` if that Python executable does not exist.
4. Calls the main script with the selected PDF path. The script displays the
   conversion-only options prompt before it creates output or moves originals:

```bat
"C:\LocalVenvs\pdfconvertOCR\Scripts\python.exe" "C:\Utils\pdfconvertOCR\pdf_automation_v6.2.py" "C:\path\to\selected.pdf"
```

## Python entry point

`pdf_automation_v6.2.py` checks command-line arguments in `main()`:

- If one or more arguments end in `.pdf`, it treats them as selected files.
- It preserves the lexical selected pathname instead of resolving it through a
  link. The shared processing boundary rejects symbolic links, junctions,
  redirecting reparse points, multiply linked files, and NTFS alternate data
  streams.
- Each valid file is passed to `process_single()`.
- Processing uses a private snapshot of the verified source identity and
  revalidates that identity before output publication and before the source is
  kept, copied, or moved.
- Resource admission limits for input size, page complexity, aggregate batch
  work, retained diagnostics, and whole-operation duration remain planned.
  Existing child-process timeouts do not bound every in-process parser step.
- `process_single()` writes the OCR output next to the original as `<name>_OCR.pdf`.
- The output PDF's Modified Date is set to match the source PDF after OCR and page numbering complete. The Archival PDF/A preset intentionally omits page numbers so the OCRmyPDF-generated archival output is not modified afterward.
- The original file is moved into an `Originals` folder next to the selected PDF.
- If no PDF arguments are provided, the script falls back to batch mode.

## Installing the right-click action

From Explorer:

1. Open `C:\Utils\pdfconvertOCR`.
2. Double-click `install_right_click_context.bat`.
3. Wait for the setup window to report completion.
4. Right-click a PDF and choose `Convert to OCR (v6.2)`.

Manual registry-only install from an elevated terminal:

```bat
reg import C:\Utils\pdfconvertOCR\registry\add_OCR_context_v6.2.reg
```

## Updating the implementation

If the project moves, update these hard-coded paths:

- `registry/add_OCR_context_v6.2.reg`: `C:\\Utils\\pdfconvertOCR\\run_single_pdf.bat`
- `run_single_pdf.bat`: source-checkout fallback path `C:\LocalVenvs\pdfconvertOCR\Scripts\python.exe`
- `installer/PDFConvertOCR.iss`: packaged install metadata, output name, registry command, and installed file list
- `requirements-lock.txt`: complete accepted Python dependency set and hashes
- `trusted-artifacts.json`: approved Python/build/native runtime identities and vendor tree digests

Treat `requirements-lock.txt` and `trusted-artifacts.json` as reviewed security
policy, not generated cache files. When a dependency or runtime intentionally
changes, verify its upstream provenance, rebuild the vendor payload, update only
the affected lock or manifest entries, and review the diff before release.

If the visible menu label changes, update the registry default value:

```reg
@="Convert to OCR (v6.2)"
```

If the command key name changes, use the same key name for both the verb and its `command` subkey.

## Removing the right-click action

The double-click remover is:

```text
uninstall_right_click_context.bat
```

The current installer creates this key:

```reg
HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2
```

The manual `.reg` add file creates this key:

```reg
HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2
```

A matching removal file should delete that same key:

```reg
Windows Registry Editor Version 5.00

[-HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.2]
```

After importing a removal file, restart Explorer or sign out and back in if the menu item still appears.

## Troubleshooting

- If the menu item does not appear, confirm the `.reg` file imported successfully and that it was imported with sufficient permissions.
- If clicking the menu item opens a terminal and fails, run `run_single_pdf.bat "C:\path\to\file.pdf"` manually to see the error.
- If the batch file cannot find Python, run `powershell -ExecutionPolicy Bypass -File C:\Utils\pdfconvertOCR\bootstrap.ps1`.
- If a packaged install cannot find Python packages, for example `ModuleNotFoundError: No module named 'fitz'`, rerun the installer or run `setup_installed_app.ps1` from the install folder. The setup script first rejects any changed, missing, extra, or reparse-point-backed vendor payload, then reinstalls the verified Python runtime and exact offline wheel set.
- If bootstrap rejects an existing source environment, run `bootstrap.ps1 -VerifyOnly` to identify the mismatch. Use `bootstrap.ps1 -Recreate` only when the approved source Python is intact and replacement is intended.
- If setup or build reports an integrity, tree-digest, reparse-point, or signer error, do not bypass it. Restore the reviewed payload or obtain a fresh trusted installer.
- If another `ocrmypdf.exe` exists on PATH but conversion reports OCRmyPDF missing, install it through `bootstrap.ps1` or packaged setup. Arbitrary PATH and other-user copies are intentionally ignored.
- If a selected PDF is rejected as linked, redirected, or changed, use the
  original ordinary file or copy the completed PDF to a normal local filename.
  Link-backed inputs are intentionally not followed.
- If OCRmyPDF reports `Could not find program 'pngquant' on the PATH` from a source checkout, run `choco install pngquant -y` from an elevated PowerShell window.
- If paths contain spaces, keep every `%L`, `%1`, script path, and PDF path wrapped in quotes.
