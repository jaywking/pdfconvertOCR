param(
    [switch]$Recreate,
    [switch]$VerifyOnly
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
$RequirementsLock = Join-Path $ProjectRoot "requirements-lock.txt"
$PolicyPath = Join-Path $ProjectRoot "trusted-artifacts.json"
. (Join-Path $ProjectRoot "trusted_artifacts.ps1")
$Policy = Get-TrustedArtifactPolicy -Path $PolicyPath

if (-not (Test-Path -LiteralPath $RequirementsLock -PathType Leaf)) {
    throw "Hash-locked requirements file not found: $RequirementsLock"
}

function Get-ApprovedSourcePython {
    $sourcePython = [Environment]::ExpandEnvironmentVariables($Policy.buildTools.sourcePython.path)
    $sourceRoot = Split-Path -Parent $sourcePython
    Assert-NoReparsePoint -Path $sourcePython -Label "source Python"
    Assert-FileSha256 -Path $sourcePython -ExpectedSha256 $Policy.buildTools.sourcePython.sha256 -Label "source Python"
    Assert-AuthenticodeSigner -Path $sourcePython -SubjectContains $Policy.buildTools.sourcePython.signerSubjectContains -Label "source Python"
    Assert-FileSha256 -Path (Join-Path $sourceRoot "python314.dll") -ExpectedSha256 $Policy.buildTools.sourcePython.pythonDllSha256 -Label "source Python DLL"
    Assert-FileSha256 -Path (Join-Path $sourceRoot "python3.dll") -ExpectedSha256 $Policy.buildTools.sourcePython.stableDllSha256 -Label "source stable ABI DLL"
    Assert-DirectoryTreeSha256 -Path (Join-Path $sourceRoot "Lib\venv") -ExpectedSha256 $Policy.buildTools.sourcePython.venvTreeSha256 -Label "source venv module"
    Assert-DirectoryTreeSha256 -Path (Join-Path $sourceRoot "Lib\ensurepip") -ExpectedSha256 $Policy.buildTools.sourcePython.ensurepipTreeSha256 -Label "source ensurepip module"
    return $sourcePython
}

function New-ProjectVenv {
    param([string]$TargetPath, [string]$SourcePython)

    & $SourcePython -I -S -m venv $TargetPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $TargetPath "Scripts\python.exe") -PathType Leaf)) {
        throw "Unable to create a virtual environment at $TargetPath with the approved Python runtime."
    }
}

function Invoke-IsolatedPip {
    param([string[]]$Arguments)

    $pipPackage = Join-Path $VenvPath "Lib\site-packages\pip"
    if (-not (Test-Path -LiteralPath $pipPackage -PathType Container)) {
        throw "Trusted pip package was not created at $pipPackage"
    }
    $temporaryPipRoot = Join-Path ([IO.Path]::GetTempPath()) ("pdfconvert-pip-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $temporaryPipRoot | Out-Null
    try {
        Copy-Item -LiteralPath $pipPackage -Destination $temporaryPipRoot -Recurse
        $pipCode = "import sys; sys.path.insert(0, r'$temporaryPipRoot'); from pip._internal.cli.main import main; raise SystemExit(main())"
        & $PythonExe -I -S -c $pipCode @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Hash-locked dependency installation failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Remove-Item -LiteralPath $temporaryPipRoot -Recurse -Force
    }
}

$SourcePython = Get-ApprovedSourcePython
New-Item -ItemType Directory -Path $VenvRoot -Force | Out-Null
if ($Recreate -and (Test-Path -LiteralPath $VenvPath)) {
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    New-ProjectVenv -TargetPath $VenvPath -SourcePython $SourcePython
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Virtual environment was not created at $VenvPath"
}

Assert-AuthenticodeSigner -Path $PythonExe -SubjectContains $Policy.python.signerSubjectContains -Label "project virtual-environment Python"
Assert-NoReparsePoint -Path $PythonExe -Label "project virtual-environment Python"
Assert-FileSha256 -Path $PythonExe -ExpectedSha256 $Policy.buildTools.python.sha256 -Label "project virtual-environment Python"
$venvConfig = Get-Content -LiteralPath (Join-Path $VenvPath "pyvenv.cfg") -Raw
$expectedSourceRoot = Split-Path -Parent ([Environment]::ExpandEnvironmentVariables($Policy.buildTools.sourcePython.path))
if ($venvConfig -notmatch "(?m)^home = $([regex]::Escape($expectedSourceRoot))\r?$" -or
    $venvConfig -notmatch "(?m)^version = $([regex]::Escape($Policy.buildTools.sourcePython.version))\r?$") {
    throw "Project virtual environment is not based on the approved source Python runtime."
}
if ($VerifyOnly) {
    Write-Host "Verified source runtime, project Python, and hash-locked dependency policy; no packages were installed."
    return
}

$sitePackages = Join-Path $VenvPath "Lib\site-packages"
if (Test-Path -LiteralPath (Join-Path $sitePackages "pip")) {
    Remove-Item -LiteralPath (Join-Path $sitePackages "pip") -Recurse -Force
}
Get-ChildItem -LiteralPath $sitePackages -Filter "pip-*.dist-info" -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
& $PythonExe -I -S -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) {
    throw "Trusted pip bootstrap failed with exit code $LASTEXITCODE."
}
Invoke-IsolatedPip -Arguments @(
    "install", "--require-hashes", "--only-binary=:all:", "-r", $RequirementsLock
)

& $PythonExe -c "import pymupdf, ocrmypdf; print('Runtime OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Runtime import verification failed with exit code $LASTEXITCODE."
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Virtual environment: $VenvPath"
Write-Host "Python executable: $PythonExe"
