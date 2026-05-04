# Right-Click Context Menu Implementation

This project implements the Explorer right-click action with three pieces:

1. A Windows Registry shell verb for `.pdf` files.
2. A batch wrapper that receives the selected PDF path from Explorer.
3. The Python script's single-file mode.

## Files involved

- `registry/add_OCR_context_v6.1.reg` adds the Explorer menu item.
- `install_right_click_context.bat` is the double-click installer for the Explorer menu item.
- `install_right_click_context.ps1` bootstraps the project and writes the user-level registry keys.
- `uninstall_right_click_context.bat` removes the Explorer menu item.
- `run_single_pdf.bat` is the command Explorer runs.
- `bootstrap.ps1` creates or repairs the centralized virtual environment if it is missing.
- `pdf_automation_v6.1.py` processes the selected PDF when given a PDF path argument.

## Double-click installer

The easiest way to install the right-click action is to double-click:

```text
install_right_click_context.bat
```

That batch file runs `install_right_click_context.ps1` with `-ExecutionPolicy Bypass`. The PowerShell installer:

1. Confirms the expected project files exist.
2. Runs `bootstrap.ps1` to create or repair `C:\LocalVenvs\pdfconvert`.
3. Creates the Explorer PDF shell verb under the current user's registry hive.
4. Points that shell verb at this repo's `run_single_pdf.bat`.

The installer uses this user-level registry path:

```text
HKCU\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1
```

Using `HKCU` keeps the install scoped to the current Windows user and usually avoids needing an elevated terminal.

## Manual registry verb

The older/manual install path is to import `registry/add_OCR_context_v6.1.reg`:

```reg
Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1]
@="Convert to OCR (v6.1)"
"Icon"="C:\\Windows\\System32\\imageres.dll,-5302"
"MultiSelectModel"="Document"

[HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1\command]
@="\"C:\\Utils\\pdfconvert\\run_single_pdf.bat\" \"%L\""
```

What each part does:

- `HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1` registers a shell command for PDF files.
- The default value, `Convert to OCR (v6.1)`, is the label shown in Explorer.
- `Icon` chooses the icon shown next to the menu item.
- `MultiSelectModel=Document` allows the command to appear when multiple PDF documents are selected.
- The `command` default value is the executable command Explorer runs.
- `%L` is replaced by Explorer with the selected PDF's long file path. It is quoted so paths with spaces work.

## Command flow

When a user selects a PDF and chooses `Convert to OCR (v6.1)`, Explorer runs:

```bat
"C:\Utils\pdfconvert\run_single_pdf.bat" "C:\path\to\selected.pdf"
```

`run_single_pdf.bat` then:

1. Sets the project root from the batch file location.
2. Looks for `C:\LocalVenvs\pdfconvert\Scripts\python.exe`.
3. Runs `bootstrap.ps1` if that Python executable does not exist.
4. Calls the main script with the selected PDF path:

```bat
"C:\LocalVenvs\pdfconvert\Scripts\python.exe" "C:\Utils\pdfconvert\pdf_automation_v6.1.py" "C:\path\to\selected.pdf"
```

## Python entry point

`pdf_automation_v6.1.py` checks command-line arguments in `main()`:

- If one or more arguments end in `.pdf`, it treats them as selected files.
- Each valid file is passed to `process_single()`.
- `process_single()` writes the OCR output next to the original as `<name>_OCR.pdf`.
- The original file is moved into an `Originals` folder next to the selected PDF.
- If no PDF arguments are provided, the script falls back to batch mode.

## Installing the right-click action

From Explorer:

1. Open `C:\Utils\pdfconvert`.
2. Double-click `install_right_click_context.bat`.
3. Wait for the setup window to report completion.
4. Right-click a PDF and choose `Convert to OCR (v6.1)`.

Manual registry-only install from an elevated terminal:

```bat
reg import C:\Utils\pdfconvert\registry\add_OCR_context_v6.1.reg
```

## Updating the implementation

If the project moves, update these hard-coded paths:

- `registry/add_OCR_context_v6.1.reg`: `C:\\Utils\\pdfconvert\\run_single_pdf.bat`
- `run_single_pdf.bat`: `C:\LocalVenvs\pdfconvert\Scripts\python.exe`
- `pdf_automation_v6.1.py`: `BASE_DIR = Path(r"C:\\Utils\\pdfconvert")`

If the visible menu label changes, update the registry default value:

```reg
@="Convert to OCR (v6.1)"
```

If the command key name changes, use the same key name for both the verb and its `command` subkey.

## Removing the right-click action

The double-click remover is:

```text
uninstall_right_click_context.bat
```

The current installer creates this key:

```reg
HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1
```

The manual `.reg` add file creates this key:

```reg
HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1
```

A matching removal file should delete that same key:

```reg
Windows Registry Editor Version 5.00

[-HKEY_CLASSES_ROOT\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1]
```

After importing a removal file, restart Explorer or sign out and back in if the menu item still appears.

## Troubleshooting

- If the menu item does not appear, confirm the `.reg` file imported successfully and that it was imported with sufficient permissions.
- If clicking the menu item opens a terminal and fails, run `run_single_pdf.bat "C:\path\to\file.pdf"` manually to see the error.
- If the batch file cannot find Python, run `powershell -ExecutionPolicy Bypass -File C:\Utils\pdfconvert\bootstrap.ps1`.
- If OCRmyPDF reports `Could not find program 'pngquant' on the PATH`, run `choco install pngquant` from an elevated PowerShell window.
- If paths contain spaces, keep every `%L`, `%1`, script path, and PDF path wrapped in quotes.
