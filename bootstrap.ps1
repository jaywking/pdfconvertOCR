param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = Split-Path -Leaf $ProjectRoot
$VenvRoot = "C:\LocalVenvs"
$VenvPath = Join-Path $VenvRoot $ProjectName
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$PyProjectPath = Join-Path $ProjectRoot "pyproject.toml"

function New-ProjectVenv {
    param(
        [string]$TargetPath
    )

    $created = $false

    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($launcherArgs in @(
            @("-3.12", "-m", "venv", $TargetPath),
            @("-3", "-m", "venv", $TargetPath),
            @("-m", "venv", $TargetPath)
        )) {
            try {
                & py @launcherArgs
                if ($LASTEXITCODE -eq 0) {
                    $created = $true
                    break
                }
            }
            catch {
            }
        }
    }

    if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -m venv $TargetPath
        $created = $LASTEXITCODE -eq 0
    }

    if (-not $created) {
        throw "Unable to create a virtual environment at $TargetPath"
    }
}

New-Item -ItemType Directory -Path $VenvRoot -Force | Out-Null

if ($Recreate -and (Test-Path $VenvPath)) {
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}

if (-not (Test-Path $PythonExe)) {
    New-ProjectVenv -TargetPath $VenvPath
}

if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment was not created at $VenvPath"
}

& $PythonExe -m pip install --upgrade pip

if (Test-Path $RequirementsPath) {
    & $PythonExe -m pip install -r $RequirementsPath
} elseif (Test-Path $PyProjectPath) {
    & $PythonExe -m pip install .
} else {
    Write-Host "No requirements.txt or pyproject.toml found. Skipping dependency install."
}

$playwrightNeeded = $false

if (Test-Path $RequirementsPath) {
    $playwrightNeeded = Select-String -Path $RequirementsPath -Pattern "(^|[\\s])playwright([<>=~!]|$)" -Quiet
}

if (-not $playwrightNeeded -and (Test-Path $PyProjectPath)) {
    $playwrightNeeded = Select-String -Path $PyProjectPath -Pattern "playwright" -Quiet
}

if ($playwrightNeeded) {
    & $PythonExe -m playwright install
} else {
    Write-Host "Playwright not detected. Skipping browser install."
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Virtual environment: $VenvPath"
Write-Host "Python executable: $PythonExe"
