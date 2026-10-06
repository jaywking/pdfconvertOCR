param([switch]$VerifyOnly)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SetupLog = Join-Path $AppRoot "setup_runtime.log"
Start-Transcript -LiteralPath $SetupLog -Force | Out-Null
$WindowsPowerShellModules = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\Modules"
if (-not (Test-Path -LiteralPath $WindowsPowerShellModules -PathType Container)) {
    throw "Windows PowerShell module directory not found: $WindowsPowerShellModules"
}
$env:PSModulePath = $WindowsPowerShellModules
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
$PythonDir = Join-Path $AppRoot "python"
$PythonExe = Join-Path $PythonDir "python.exe"
$PolicyPath = Join-Path $AppRoot "trusted-artifacts.json"
$RequirementsLock = Join-Path $AppRoot "requirements-lock.txt"
$Wheelhouse = Join-Path $AppRoot "vendor\wheelhouse"
. (Join-Path $AppRoot "trusted_artifacts.ps1")
$Policy = Get-TrustedArtifactPolicy -Path $PolicyPath
$PythonVendor = Join-Path $AppRoot "vendor\python"
$PythonInstaller = Join-Path $PythonVendor $Policy.python.installerName

Write-Host "PDFConvertOCR install folder: $AppRoot"

# Verify every packaged executable tree before running the Python installer or
# importing any Python package. Extra, missing, changed, or linked files fail.
Assert-DirectoryTreeSha256 -Path $PythonVendor -ExpectedSha256 $Policy.python.vendorTreeSha256 -Label "Python vendor payload"
Assert-FileSha256 -Path $PythonInstaller -ExpectedSha256 $Policy.python.installerSha256 -Label "bundled Python installer"
Assert-AuthenticodeSigner -Path $PythonInstaller -SubjectContains $Policy.python.signerSubjectContains -Label "bundled Python installer"
Assert-DirectoryTreeSha256 -Path $Wheelhouse -ExpectedSha256 $Policy.wheelhouse.treeSha256 -Label "wheelhouse"
$wheelCount = @(Get-ChildItem -LiteralPath $Wheelhouse -File).Count
if ($wheelCount -ne $Policy.wheelhouse.fileCount) {
    throw "Wheelhouse contains $wheelCount files; expected $($Policy.wheelhouse.fileCount)."
}
Assert-DirectoryTreeSha256 -Path (Join-Path $AppRoot "vendor\ghostscript") -ExpectedSha256 $Policy.runtimes.ghostscript.treeSha256 -Label "Ghostscript vendor payload"
Assert-DirectoryTreeSha256 -Path (Join-Path $AppRoot "vendor\tesseract") -ExpectedSha256 $Policy.runtimes.tesseract.treeSha256 -Label "Tesseract vendor payload"
Assert-DirectoryTreeSha256 -Path (Join-Path $AppRoot "vendor\pngquant") -ExpectedSha256 $Policy.runtimes.pngquant.treeSha256 -Label "pngquant vendor payload"

if ($VerifyOnly) {
    Write-Host "Verified all packaged runtime payloads; installation was skipped."
    Stop-Transcript | Out-Null
    Remove-Item -LiteralPath $SetupLog -Force
    return
}

# A repair never executes a pre-existing runtime. Reinstalling from the verified
# offline payload keeps the trust boundary at the checked installer and lock.
if (Test-Path -LiteralPath $PythonDir) {
    $pythonItem = Get-Item -LiteralPath $PythonDir -Force
    if (($pythonItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to replace a linked Python runtime directory: $PythonDir"
    }
    $resolvedApp = [IO.Path]::GetFullPath($AppRoot).TrimEnd("\")
    $resolvedPython = [IO.Path]::GetFullPath($PythonDir)
    if (-not $resolvedPython.StartsWith($resolvedApp + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace Python outside the application folder: $resolvedPython"
    }
    Remove-Item -LiteralPath $PythonDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null

# Extract a private runtime without registering the CPython bundle. Running the
# bundle directly enters maintenance mode when the same Python feature release
# is already installed for the user and can modify that unrelated installation
# instead of populating TargetDir. Administrative MSI extraction is side-by-side
# safe and does not register products, file associations, or PATH entries.
$PythonComponents = @("core.msi", "exe.msi", "lib.msi", "tcltk.msi", "ucrt.msi")
$WindowsInstaller = Join-Path $env:SystemRoot "System32\msiexec.exe"
Write-Host "Extracting verified bundled Python runtime $($Policy.python.version)..."
foreach ($componentName in $PythonComponents) {
    $componentPath = Join-Path $PythonVendor $componentName
    if (-not (Test-Path -LiteralPath $componentPath -PathType Leaf)) {
        throw "Bundled Python component is missing: $componentPath"
    }
    $arguments = @(
        "/a",
        ('"' + $componentPath + '"'),
        "/qn",
        ('TARGETDIR="' + $PythonDir + '"')
    )
    $process = Start-Process -FilePath $WindowsInstaller -ArgumentList $arguments -Wait -NoNewWindow -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Bundled Python component $componentName failed extraction with exit code $($process.ExitCode)."
    }
    $administrativeDatabase = Join-Path $PythonDir $componentName
    if (Test-Path -LiteralPath $administrativeDatabase -PathType Leaf) {
        Remove-Item -LiteralPath $administrativeDatabase -Force
    }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python runtime was not installed at $PythonExe"
}
Assert-AuthenticodeSigner -Path $PythonExe -SubjectContains $Policy.python.signerSubjectContains -Label "installed Python runtime"
$installedVersion = & $PythonExe -c "import platform; print(platform.python_version())"
if ($LASTEXITCODE -ne 0 -or $installedVersion -ne $Policy.python.version) {
    throw "Installed Python version $installedVersion does not match approved version $($Policy.python.version)."
}

& $PythonExe -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) {
    throw "pip bootstrap failed with exit code $LASTEXITCODE."
}

Write-Host "Installing verified Python packages from the offline wheelhouse..."
& $PythonExe -m pip install `
    --no-index `
    --find-links $Wheelhouse `
    --require-hashes `
    --only-binary=:all: `
    --no-deps `
    -r $RequirementsLock
if ($LASTEXITCODE -ne 0) {
    throw "Python package installation failed with exit code $LASTEXITCODE."
}

Write-Host "Verifying runtime imports..."
& $PythonExe -c "import tkinter, pymupdf, ocrmypdf; print('Runtime OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Runtime verification failed with exit code $LASTEXITCODE."
}

Write-Host "PDFConvertOCR installation setup complete."
Stop-Transcript | Out-Null
Remove-Item -LiteralPath $SetupLog -Force
