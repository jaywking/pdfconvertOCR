$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonDir = Join-Path $AppRoot "python"
$PythonExe = Join-Path $PythonDir "python.exe"
$PythonInstaller = Get-ChildItem -Path (Join-Path $AppRoot "vendor\python") -Filter "python-*-amd64.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
$Requirements = Join-Path $AppRoot "requirements.txt"
$Wheelhouse = Join-Path $AppRoot "vendor\wheelhouse"

Write-Host "PDFConvertOCR install folder: $AppRoot"

if (-not (Test-Path $PythonExe)) {
    if (-not $PythonInstaller) {
        throw "Bundled Python installer not found under vendor\python."
    }

    Write-Host "Installing bundled Python runtime..."
    New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
    $pythonArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=0",
        "Include_doc=0",
        "Include_launcher=0",
        "Include_pip=1",
        "Include_tcltk=0",
        "Include_test=0",
        "TargetDir=$PythonDir"
    )
    Start-Process -FilePath $PythonInstaller.FullName -ArgumentList $pythonArgs -Wait -NoNewWindow
}

if (-not (Test-Path $PythonExe)) {
    throw "Python runtime was not installed at $PythonExe"
}

$pipReady = $false
try {
    & $PythonExe -m pip --version
    $pipReady = ($LASTEXITCODE -eq 0)
}
catch {
    $pipReady = $false
}

if (-not $pipReady) {
    Write-Host "Bootstrapping pip in bundled Python runtime..."
    & $PythonExe -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "pip bootstrap failed."
    }
}

if (-not (Test-Path $Wheelhouse)) {
    throw "Offline wheelhouse not found at $Wheelhouse"
}

Write-Host "Installing Python packages from offline wheelhouse..."
& $PythonExe -m pip install --no-index --find-links $Wheelhouse -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Python package installation failed."
}

Write-Host "Verifying runtime imports..."
& $PythonExe -c "import fitz, ocrmypdf; print('Runtime OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Runtime verification failed."
}

Write-Host "PDFConvertOCR installation setup complete."
