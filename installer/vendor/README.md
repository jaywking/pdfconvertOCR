# Vendor Runtime Payloads

The installer build script populates this folder with offline runtime dependencies before compiling the setup EXE.

Expected generated folders:

- `python/`: bundled Python installer
- `wheelhouse/`: Python wheels for `requirements.txt`
- `ghostscript/`: Ghostscript runtime copied from the build machine
- `tesseract/`: Tesseract runtime copied from the build machine, including `tessdata`
- `pngquant/`: `pngquant.exe`
- `THIRD_PARTY_NOTICES.txt`: generated dependency license notes

These payloads are intentionally not committed to git because they are large third-party binaries. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
```

Review third-party licenses before distributing a public installer, especially Ghostscript's AGPL/commercial licensing.
