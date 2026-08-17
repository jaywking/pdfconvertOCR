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

if (-not $PythonInstaller) {
    throw "Bundled Python installer not found under vendor\python."
}
if ($PythonInstaller.BaseName -notmatch '^python-(\d+\.\d+\.\d+)-amd64$') {
    throw "Could not determine bundled Python version from $($PythonInstaller.Name)"
}
$ExpectedPythonVersion = $Matches[1]
$PythonInstallOptions = @(
    "InstallAllUsers=0",
    "AssociateFiles=0",
    "PrependPath=0",
    "Include_dev=0",
    "Include_doc=0",
    "Include_launcher=0",
    "Include_pip=1",
    "Shortcuts=0",
    "Include_tcltk=1",
    "Include_test=0",
    "TargetDir=$PythonDir"
)
$RepairPythonRuntime = $false

if (Test-Path $PythonExe) {
    $InstalledPythonVersion = $null
    $TkinterReady = $false
    try {
        $InstalledPythonVersion = & $PythonExe -c "import platform; print(platform.python_version())"
        if ($LASTEXITCODE -ne 0) {
            $InstalledPythonVersion = $null
        }
    }
    catch {
        $InstalledPythonVersion = $null
    }
    if ($InstalledPythonVersion -eq $ExpectedPythonVersion) {
        try {
            & $PythonExe -c "import tkinter" 2>$null
            $TkinterReady = ($LASTEXITCODE -eq 0)
        }
        catch {
            $TkinterReady = $false
        }
    }
    if ($InstalledPythonVersion -ne $ExpectedPythonVersion) {
        Write-Host "Replacing Python runtime because version $InstalledPythonVersion does not match $ExpectedPythonVersion..."
        Remove-Item -LiteralPath $PythonDir -Recurse -Force
    } elseif (-not $TkinterReady) {
        $RepairPythonRuntime = $true
    }
}

if ($RepairPythonRuntime) {
    Write-Host "Repairing bundled Python runtime to add Tcl/Tk support..."
    $pythonRepairArgs = @("/repair", "/quiet") + $PythonInstallOptions
    $PythonRepairProcess = Start-Process -FilePath $PythonInstaller.FullName -ArgumentList $pythonRepairArgs -Wait -NoNewWindow -PassThru
    if ($PythonRepairProcess.ExitCode -ne 0) {
        throw "Bundled Python repair failed with exit code $($PythonRepairProcess.ExitCode)."
    }
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "Installing bundled Python runtime $ExpectedPythonVersion..."
    New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
    $pythonArgs = @("/quiet") + $PythonInstallOptions
    $PythonInstallProcess = Start-Process -FilePath $PythonInstaller.FullName -ArgumentList $pythonArgs -Wait -NoNewWindow -PassThru
    if ($PythonInstallProcess.ExitCode -ne 0) {
        throw "Bundled Python installer failed with exit code $($PythonInstallProcess.ExitCode)."
    }
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
& $PythonExe -c "import tkinter, pymupdf, ocrmypdf; print('Runtime OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Runtime verification failed."
}

Write-Host "PDFConvertOCR installation setup complete."
