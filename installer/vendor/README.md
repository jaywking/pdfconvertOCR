# Vendor Runtime Payloads

The installer build script populates this folder with offline runtime dependencies before compiling the setup EXE.

Expected generated folders:

- `python/`: bundled Python installer
- `wheelhouse/`: Python wheels for `requirements-lock.txt`
- `ghostscript/`: Ghostscript runtime copied from the build machine
- `tesseract/`: Tesseract runtime copied from the build machine, including `tessdata`
- `pngquant/`: `pngquant.exe`
- `THIRD_PARTY_NOTICES.txt`: generated dependency license notes

These payloads are intentionally not committed to git because they are large
third-party binaries. Their reviewed SHA-256 tree digests and source locations
are committed in `trusted-artifacts.json`; Python dependencies are fully pinned
in `requirements-lock.txt`. The build refuses changed, missing, extra, or
reparse-point-backed payload files, including when `-SkipVendorRefresh` is used. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
```

Verify the approved build tools and current staged payload without refreshing
or compiling:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 -VerifyOnly
```

Compile from the current staging tree with
`build_installer.ps1 -SkipVendorRefresh`; that switch still performs the full
payload verification. An integrity failure must be investigated. Never replace
a committed digest solely to make an unexpected local file pass.

The staged Ghostscript runtime must match the exact version, executable hash,
license path, corresponding-source URL, and source archive checksums recorded
in `trusted-artifacts.json`. The generated `THIRD_PARTY_NOTICES.txt` carries
the same source directions into the installed application. Each public release
that contains Ghostscript must also provide the recorded source archive as a
release asset.
