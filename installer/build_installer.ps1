param(
    [string]$Version,
    [string]$PythonVersion = "3.14.7",
    [switch]$SkipVendorRefresh,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}
if (Get-Variable PSNativeCommandArgumentPassing -ErrorAction SilentlyContinue) {
    $PSNativeCommandArgumentPassing = "Standard"
}

$InstallerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $InstallerRoot
$MetadataPath = Join-Path $ProjectRoot "app_metadata.json"
$PolicyPath = Join-Path $ProjectRoot "trusted-artifacts.json"
$IntegrityScript = Join-Path $ProjectRoot "trusted_artifacts.ps1"
$RequirementsLock = Join-Path $ProjectRoot "requirements-lock.txt"
. $IntegrityScript

$Metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
$Policy = Get-TrustedArtifactPolicy -Path $PolicyPath
if (-not $Version) {
    $Version = $Metadata.appVersion
}
if ($PythonVersion -ne $Policy.python.version) {
    throw "PythonVersion $PythonVersion is not approved by trusted-artifacts.json (expected $($Policy.python.version))."
}

$PythonVersionParts = $PythonVersion.Split(".")
$PythonFeatureVersion = "$($PythonVersionParts[0]).$($PythonVersionParts[1])"
$PythonAbi = "cp$($PythonVersionParts[0])$($PythonVersionParts[1])"
$VendorRoot = Join-Path $InstallerRoot "vendor"
$CacheRoot = Join-Path $InstallerRoot "cache"
$DistRoot = Join-Path $ProjectRoot "dist"
$IssPath = Join-Path $InstallerRoot "PDFConvertOCR.iss"

function Copy-CleanDirectory {
    param([string]$Source, [string]$Destination)

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Source folder not found: $Source"
    }
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Save-TrustedUrl {
    param(
        [string]$Url,
        [string]$Destination,
        [string]$ExpectedSha256,
        [string]$SignerSubjectContains
    )

    if (-not (Test-Path -LiteralPath $Destination)) {
        $temporary = "$Destination.download"
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $temporary
        Assert-FileSha256 -Path $temporary -ExpectedSha256 $ExpectedSha256 -Label "downloaded Python installer"
        Assert-AuthenticodeSigner -Path $temporary -SubjectContains $SignerSubjectContains -Label "downloaded Python installer"
        Move-Item -LiteralPath $temporary -Destination $Destination
    }
    Assert-FileSha256 -Path $Destination -ExpectedSha256 $ExpectedSha256 -Label "cached Python installer"
    Assert-AuthenticodeSigner -Path $Destination -SubjectContains $SignerSubjectContains -Label "cached Python installer"
}

function Save-TrustedFile {
    param(
        [string]$Url,
        [string]$Destination,
        [string]$ExpectedSha256,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Destination)) {
        $temporary = "$Destination.download"
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $temporary
        Assert-FileSha256 -Path $temporary -ExpectedSha256 $ExpectedSha256 -Label $Label
        Move-Item -LiteralPath $temporary -Destination $Destination
    }
    Assert-FileSha256 -Path $Destination -ExpectedSha256 $ExpectedSha256 -Label $Label
}

function Initialize-PythonOfflineLayout {
    param(
        [string]$InstallerPath,
        [string]$LayoutPath,
        [string[]]$RequiredFiles
    )

    New-Item -ItemType Directory -Path $LayoutPath -Force | Out-Null
    $missingFiles = @($RequiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $LayoutPath $_) -PathType Leaf) })
    if ($missingFiles.Count -gt 0) {
        Write-Host "Preparing verified offline Python layout for $PythonVersion..."
        $layoutArgs = @(
            "/layout", $LayoutPath, "/quiet", "InstallAllUsers=0", "AssociateFiles=0",
            "PrependPath=0", "Include_dev=0", "Include_doc=0", "Include_launcher=0",
            "Include_pip=1", "Shortcuts=0", "Include_tcltk=1", "Include_test=0"
        )
        $process = Start-Process -FilePath $InstallerPath -ArgumentList $layoutArgs -Wait -NoNewWindow -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Python offline layout failed with exit code $($process.ExitCode)."
        }
    }
    $stillMissing = @($RequiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $LayoutPath $_) -PathType Leaf) })
    if ($stillMissing.Count -gt 0) {
        throw "Python offline layout is incomplete. Missing: $($stillMissing -join ', ')"
    }
}

function Assert-VendorPayload {
    $pythonVendor = Join-Path $VendorRoot "python"
    $wheelhouse = Join-Path $VendorRoot "wheelhouse"
    $ghostscriptVendor = Join-Path $VendorRoot "ghostscript"
    $tesseractVendor = Join-Path $VendorRoot "tesseract"
    $pngquantVendor = Join-Path $VendorRoot "pngquant"

    Assert-DirectoryTreeSha256 -Path $pythonVendor -ExpectedSha256 $Policy.python.vendorTreeSha256 -Label "Python vendor payload"
    $bundledInstaller = Join-Path $pythonVendor $Policy.python.installerName
    Assert-FileSha256 -Path $bundledInstaller -ExpectedSha256 $Policy.python.installerSha256 -Label "bundled Python installer"
    Assert-AuthenticodeSigner -Path $bundledInstaller -SubjectContains $Policy.python.signerSubjectContains -Label "bundled Python installer"
    Assert-DirectoryTreeSha256 -Path $wheelhouse -ExpectedSha256 $Policy.wheelhouse.treeSha256 -Label "wheelhouse"
    $wheelCount = @(Get-ChildItem -LiteralPath $wheelhouse -File).Count
    if ($wheelCount -ne $Policy.wheelhouse.fileCount) {
        throw "Wheelhouse contains $wheelCount files; expected $($Policy.wheelhouse.fileCount)."
    }
    Assert-DirectoryTreeSha256 -Path $ghostscriptVendor -ExpectedSha256 $Policy.runtimes.ghostscript.treeSha256 -Label "Ghostscript vendor payload"
    $ghostscriptExecutable = Join-Path $ghostscriptVendor $Policy.runtimes.ghostscript.executableRelativePath
    Assert-FileSha256 -Path $ghostscriptExecutable -ExpectedSha256 $Policy.runtimes.ghostscript.executableSha256 -Label "Ghostscript executable"
    $ghostscriptVersion = (Get-Item -LiteralPath $ghostscriptExecutable).VersionInfo.FileVersion
    if ($ghostscriptVersion -ne $Policy.runtimes.ghostscript.version) {
        throw "Ghostscript executable version $ghostscriptVersion does not match approved version $($Policy.runtimes.ghostscript.version)."
    }
    $ghostscriptLicense = Join-Path $ghostscriptVendor $Policy.runtimes.ghostscript.licenseRelativePath
    if (-not (Test-Path -LiteralPath $ghostscriptLicense -PathType Leaf)) {
        throw "Ghostscript AGPL license not found: $ghostscriptLicense"
    }
    Assert-DirectoryTreeSha256 -Path $tesseractVendor -ExpectedSha256 $Policy.runtimes.tesseract.treeSha256 -Label "Tesseract vendor payload"
    Assert-DirectoryTreeSha256 -Path $pngquantVendor -ExpectedSha256 $Policy.runtimes.pngquant.treeSha256 -Label "pngquant vendor payload"
}

function New-IsccStringDefine {
    param([string]$Name, [string]$Value)
    return ('/D{0}={1}' -f $Name, $Value)
}

function Get-ApprovedBuildPython {
    $sourcePython = [Environment]::ExpandEnvironmentVariables($Policy.buildTools.sourcePython.path)
    $sourceRoot = Split-Path -Parent $sourcePython
    Assert-NoReparsePoint -Path $sourcePython -Label "source Python"
    Assert-FileSha256 -Path $sourcePython -ExpectedSha256 $Policy.buildTools.sourcePython.sha256 -Label "source Python"
    Assert-AuthenticodeSigner -Path $sourcePython -SubjectContains $Policy.buildTools.sourcePython.signerSubjectContains -Label "source Python"
    Assert-FileSha256 -Path (Join-Path $sourceRoot "python314.dll") -ExpectedSha256 $Policy.buildTools.sourcePython.pythonDllSha256 -Label "source Python DLL"
    Assert-FileSha256 -Path (Join-Path $sourceRoot "python3.dll") -ExpectedSha256 $Policy.buildTools.sourcePython.stableDllSha256 -Label "source stable ABI DLL"
    Assert-DirectoryTreeSha256 -Path (Join-Path $sourceRoot "Lib\venv") -ExpectedSha256 $Policy.buildTools.sourcePython.venvTreeSha256 -Label "source venv module"
    Assert-DirectoryTreeSha256 -Path (Join-Path $sourceRoot "Lib\ensurepip") -ExpectedSha256 $Policy.buildTools.sourcePython.ensurepipTreeSha256 -Label "source ensurepip module"

    $buildPython = $Policy.buildTools.python.path
    Assert-NoReparsePoint -Path $buildPython -Label "build Python"
    Assert-FileSha256 -Path $buildPython -ExpectedSha256 $Policy.buildTools.python.sha256 -Label "build Python"
    Assert-AuthenticodeSigner -Path $buildPython -SubjectContains $Policy.buildTools.python.signerSubjectContains -Label "build Python"
    $buildRoot = Split-Path -Parent (Split-Path -Parent $buildPython)
    Assert-FileSha256 -Path (Join-Path $buildRoot "pyvenv.cfg") -ExpectedSha256 $Policy.buildTools.python.pyvenvConfigSha256 -Label "build Python configuration"
    Assert-DirectoryTreeSha256 -Path (Join-Path $buildRoot "Lib\site-packages\pip") -ExpectedSha256 $Policy.buildTools.python.pipTreeSha256 -Label "build pip package"
    Assert-DirectoryTreeSha256 -Path (Join-Path $buildRoot "Lib\site-packages\pip-$($Policy.buildTools.python.pipVersion).dist-info") -ExpectedSha256 $Policy.buildTools.python.pipMetadataTreeSha256 -Label "build pip metadata"
    return $buildPython
}

function Invoke-TrustedPipDownload {
    param([string]$BuildPython, [string]$Destination)

    $buildRoot = Split-Path -Parent (Split-Path -Parent $BuildPython)
    $pipSource = Join-Path $buildRoot "Lib\site-packages\pip"
    $temporaryPipRoot = Join-Path ([IO.Path]::GetTempPath()) ("pdfconvert-build-pip-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $temporaryPipRoot | Out-Null
    try {
        Copy-Item -LiteralPath $pipSource -Destination $temporaryPipRoot -Recurse
        Assert-DirectoryTreeSha256 -Path (Join-Path $temporaryPipRoot "pip") -ExpectedSha256 $Policy.buildTools.python.pipTreeSha256 -Label "isolated build pip copy"
        $pipCode = "import sys; sys.path.insert(0, r'$temporaryPipRoot'); from pip._internal.cli.main import main; raise SystemExit(main())"
        & $BuildPython -I -S -c $pipCode download `
            --require-hashes `
            --dest $Destination `
            --only-binary=:all: `
            --platform win_amd64 `
            --implementation cp `
            --python-version $PythonFeatureVersion `
            --abi $PythonAbi `
            -r $RequirementsLock
        if ($LASTEXITCODE -ne 0) {
            throw "Hash-locked pip download failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Remove-Item -LiteralPath $temporaryPipRoot -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $VendorRoot, $CacheRoot, $DistRoot -Force | Out-Null
$Iscc = Resolve-TrustedExecutable `
    -CandidatePaths $Policy.buildTools.iscc.candidatePaths `
    -SignerSubjectContains $Policy.buildTools.iscc.signerSubjectContains `
    -Label "Inno Setup compiler"

if (-not $SkipVendorRefresh -and -not $VerifyOnly) {
    $PythonInstallerCachePath = Join-Path $CacheRoot $Policy.python.installerName
    $PythonLayoutCachePath = Join-Path $CacheRoot "python-$PythonVersion-layout"
    $PythonVendorPath = Join-Path $VendorRoot "python"
    $PythonPayloadFiles = @(
        $Policy.python.installerName, "core.msi", "exe.msi", "lib.msi", "pip.msi", "tcltk.msi", "ucrt.msi"
    )

    Save-TrustedUrl `
        -Url $Policy.python.installerUrl `
        -Destination $PythonInstallerCachePath `
        -ExpectedSha256 $Policy.python.installerSha256 `
        -SignerSubjectContains $Policy.python.signerSubjectContains
    Initialize-PythonOfflineLayout `
        -InstallerPath $PythonInstallerCachePath `
        -LayoutPath $PythonLayoutCachePath `
        -RequiredFiles $PythonPayloadFiles

    if (Test-Path -LiteralPath $PythonVendorPath) {
        Remove-Item -LiteralPath $PythonVendorPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PythonVendorPath -Force | Out-Null
    foreach ($fileName in $PythonPayloadFiles) {
        Copy-Item -LiteralPath (Join-Path $PythonLayoutCachePath $fileName) -Destination (Join-Path $PythonVendorPath $fileName) -Force
    }

    $Wheelhouse = Join-Path $VendorRoot "wheelhouse"
    if (Test-Path -LiteralPath $Wheelhouse) {
        Remove-Item -LiteralPath $Wheelhouse -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null
    Write-Host "Preparing hash-locked offline Python wheelhouse..."
    $BuildPython = Get-ApprovedBuildPython
    Invoke-TrustedPipDownload -BuildPython $BuildPython -Destination $Wheelhouse

    Assert-DirectoryTreeSha256 -Path $Policy.runtimes.ghostscript.sourcePath -ExpectedSha256 $Policy.runtimes.ghostscript.treeSha256 -Label "approved Ghostscript source"
    Copy-CleanDirectory -Source $Policy.runtimes.ghostscript.sourcePath -Destination (Join-Path $VendorRoot "ghostscript")
    Assert-DirectoryTreeSha256 -Path $Policy.runtimes.tesseract.sourcePath -ExpectedSha256 $Policy.runtimes.tesseract.treeSha256 -Label "approved Tesseract source"
    Copy-CleanDirectory -Source $Policy.runtimes.tesseract.sourcePath -Destination (Join-Path $VendorRoot "tesseract")
    Assert-FileSha256 -Path $Policy.runtimes.pngquant.sourcePath -ExpectedSha256 $Policy.runtimes.pngquant.sourceSha256 -Label "approved pngquant source"
    $PngquantRoot = Join-Path $VendorRoot "pngquant"
    if (Test-Path -LiteralPath $PngquantRoot) {
        Remove-Item -LiteralPath $PngquantRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PngquantRoot -Force | Out-Null
    Copy-Item -LiteralPath $Policy.runtimes.pngquant.sourcePath -Destination (Join-Path $PngquantRoot "pngquant.exe") -Force

    $NoticePath = Join-Path $VendorRoot "THIRD_PARTY_NOTICES.txt"
    @"
PDFConvertOCR bundles third-party runtime components for offline installation.

Review and comply with each component's license before distributing this installer outside your organization.

Bundled components:
- Python: Python Software Foundation License. Installer downloaded from python.org.
- OCRmyPDF and Python wheels: licenses vary by package; inspect wheel metadata in vendor\wheelhouse.
- Ghostscript $($Policy.runtimes.ghostscript.version): GNU Affero General Public License version 3 or a separate Artifex commercial license.
  Bundled license: vendor\ghostscript\$($Policy.runtimes.ghostscript.licenseRelativePath)
  Corresponding source archive: $($Policy.runtimes.ghostscript.sourceUrl)
  Official checksum file: $($Policy.runtimes.ghostscript.sourceChecksumsUrl)
  Source SHA-256: $($Policy.runtimes.ghostscript.sourceSha256)
  Source SHA-512: $($Policy.runtimes.ghostscript.sourceSha512)
- Tesseract OCR: Apache 2.0 license; language data may have separate notices.
- pngquant: GPL-style open source licensing; verify the exact binary/package license for the copied executable.

All executable payloads are verified against trusted-artifacts.json before packaging.
"@ | Set-Content -LiteralPath $NoticePath -Encoding UTF8
}

# This gate is intentionally outside the refresh block: cached vendor reuse is
# allowed only when every byte still matches the repository-tracked policy.
Assert-VendorPayload
Write-Host "Verified all installer vendor payloads."
if ($VerifyOnly) {
    Write-Host "Verification complete; installer compilation was skipped."
    return
}

$GhostscriptSourceCachePath = Join-Path $CacheRoot $Policy.runtimes.ghostscript.sourceArchiveName
$GhostscriptSourceDistPath = Join-Path $DistRoot $Policy.runtimes.ghostscript.sourceArchiveName
Save-TrustedFile `
    -Url $Policy.runtimes.ghostscript.sourceUrl `
    -Destination $GhostscriptSourceCachePath `
    -ExpectedSha256 $Policy.runtimes.ghostscript.sourceSha256 `
    -Label "Ghostscript corresponding source archive"
Copy-Item -LiteralPath $GhostscriptSourceCachePath -Destination $GhostscriptSourceDistPath -Force
Assert-FileSha256 `
    -Path $GhostscriptSourceDistPath `
    -ExpectedSha256 $Policy.runtimes.ghostscript.sourceSha256 `
    -Label "staged Ghostscript corresponding source archive"
Write-Host "Staged Ghostscript corresponding source: $GhostscriptSourceDistPath"

Write-Host "Compiling installer with verified compiler $Iscc"
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
    "/O$DistRoot", $IssPath
)
& $Iscc @IsccArgs
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

Write-Host "Installer output:"
Get-ChildItem -Path $DistRoot -Filter "PDFConvertOCR-Setup-v*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 3
