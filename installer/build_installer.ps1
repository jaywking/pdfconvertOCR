param(
    [string]$Version,
    [string]$PythonVersion = "3.12.10",
    [switch]$SkipVendorRefresh
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$InstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $InstallerRoot
$MetadataPath = Join-Path $ProjectRoot "app_metadata.json"
if (-not (Test-Path $MetadataPath)) {
    throw "Missing app_metadata.json at $MetadataPath"
}
$Metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
if (-not $Version) {
    $Version = $Metadata.appVersion
}

$VendorRoot = Join-Path $InstallerRoot "vendor"
$CacheRoot = Join-Path $InstallerRoot "cache"
$DistRoot = Join-Path $ProjectRoot "dist"
$IssPath = Join-Path $InstallerRoot "PDFConvertOCR.iss"

function Resolve-RequiredCommand {
    param(
        [string]$Name,
        [string[]]$FallbackPaths = @()
    )

    $found = Get-Command $Name -ErrorAction SilentlyContinue
    if ($found) {
        return $found.Source
    }

    foreach ($path in $FallbackPaths) {
        if (Test-Path $path) {
            return $path
        }
    }

    throw "Required command not found: $Name"
}

function Copy-CleanDirectory {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path $Source)) {
        throw "Source folder not found: $Source"
    }

    if (Test-Path $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Save-Url {
    param(
        [string]$Url,
        [string]$Destination
    )

    if (Test-Path $Destination) {
        return
    }

    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}

function New-IsccStringDefine {
    param(
        [string]$Name,
        [string]$Value
    )

    return ('/D{0}="{1}"' -f $Name, ($Value -replace '"', '\"'))
}

New-Item -ItemType Directory -Path $VendorRoot, $CacheRoot, $DistRoot -Force | Out-Null

$IsccFallbacks = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$Iscc = Resolve-RequiredCommand -Name "iscc.exe" -FallbackPaths $IsccFallbacks

if (-not $SkipVendorRefresh) {
    $PythonInstallerName = "python-$PythonVersion-amd64.exe"
    $PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/$PythonInstallerName"
    $PythonInstallerCachePath = Join-Path $CacheRoot $PythonInstallerName
    $PythonVendorPath = Join-Path $VendorRoot "python"

    Save-Url -Url $PythonInstallerUrl -Destination $PythonInstallerCachePath
    New-Item -ItemType Directory -Path $PythonVendorPath -Force | Out-Null
    Copy-Item -LiteralPath $PythonInstallerCachePath -Destination (Join-Path $PythonVendorPath $PythonInstallerName) -Force

    $Wheelhouse = Join-Path $VendorRoot "wheelhouse"
    if (Test-Path $Wheelhouse) {
        Remove-Item -LiteralPath $Wheelhouse -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null

    $BuildPython = Resolve-RequiredCommand -Name "python.exe"
    Write-Host "Preparing offline Python wheelhouse..."
    & $BuildPython -m pip download `
        --dest $Wheelhouse `
        --only-binary=:all: `
        --platform win_amd64 `
        --implementation cp `
        --python-version 3.12 `
        --abi cp312 `
        -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "pip download failed."
    }

    $GhostscriptExe = Resolve-RequiredCommand -Name "gswin64c.exe"
    $GhostscriptRoot = Split-Path -Parent (Split-Path -Parent $GhostscriptExe)
    Write-Host "Copying Ghostscript runtime from $GhostscriptRoot"
    Copy-CleanDirectory -Source $GhostscriptRoot -Destination (Join-Path $VendorRoot "ghostscript")

    $TesseractExe = Resolve-RequiredCommand -Name "tesseract.exe"
    $TesseractRoot = Split-Path -Parent $TesseractExe
    Write-Host "Copying Tesseract runtime from $TesseractRoot"
    Copy-CleanDirectory -Source $TesseractRoot -Destination (Join-Path $VendorRoot "tesseract")

    $PngquantExe = Resolve-RequiredCommand -Name "pngquant.exe"
    $ChocolateyPngquantExe = "C:\ProgramData\chocolatey\lib\pngquant\tools\pngquant\pngquant.exe"
    if ($PngquantExe -like "*\chocolatey\bin\pngquant.exe" -and (Test-Path $ChocolateyPngquantExe)) {
        $PngquantExe = $ChocolateyPngquantExe
    }
    $PngquantRoot = Join-Path $VendorRoot "pngquant"
    if (Test-Path $PngquantRoot) {
        Remove-Item -LiteralPath $PngquantRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PngquantRoot -Force | Out-Null
    Copy-Item -LiteralPath $PngquantExe -Destination (Join-Path $PngquantRoot "pngquant.exe") -Force

    $NoticePath = Join-Path $VendorRoot "THIRD_PARTY_NOTICES.txt"
    @"
PDFConvertOCR bundles third-party runtime components for offline installation.

Review and comply with each component's license before distributing this installer outside your organization.

Bundled components:
- Python: Python Software Foundation License. Installer downloaded from python.org.
- OCRmyPDF and Python wheels: licenses vary by package; inspect wheel metadata in vendor\wheelhouse.
- Ghostscript: AGPL/commercial licensing from Artifex. Verify redistribution and organizational use before public distribution.
- Tesseract OCR: Apache 2.0 license; language data may have separate notices.
- pngquant: GPL-style open source licensing; verify the exact binary/package license for the copied executable.

This file is generated by installer\build_installer.ps1.
"@ | Set-Content -LiteralPath $NoticePath -Encoding UTF8
}

Write-Host "Compiling installer with $Iscc"
$IsccArgs = @(
    (New-IsccStringDefine -Name "MyAppName" -Value $Metadata.appName),
    (New-IsccStringDefine -Name "MyAppVersion" -Value $Version),
    (New-IsccStringDefine -Name "MyDisplayVersion" -Value $Metadata.displayVersion),
    (New-IsccStringDefine -Name "MyAppPublisher" -Value $Metadata.publisher),
    (New-IsccStringDefine -Name "MyMainScript" -Value $Metadata.mainScript),
    (New-IsccStringDefine -Name "MyRunnerScript" -Value $Metadata.runnerScript),
    (New-IsccStringDefine -Name "MyMenuLabel" -Value $Metadata.menuLabel),
    (New-IsccStringDefine -Name "MyContextVerb" -Value $Metadata.contextVerb),
    (New-IsccStringDefine -Name "MySetupBaseName" -Value $Metadata.setupBaseName),
    "/O$DistRoot",
    $IssPath
)
& $Iscc @IsccArgs
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed."
}

Write-Host "Installer output:"
Get-ChildItem -Path $DistRoot -Filter "PDFConvertOCR-Setup-v*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 3
