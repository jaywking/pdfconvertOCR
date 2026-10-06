Set-StrictMode -Version Latest

function Get-TrustedArtifactPolicy {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Trusted artifact policy not found: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Assert-FileSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [string]$Label = "file"
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "$Label failed SHA-256 verification: $Path (expected $ExpectedSha256, got $actual)"
    }
}

function Get-DirectoryTreeSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Directory not found: $Path"
    }
    $rootItem = Get-Item -LiteralPath $Path -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Reparse points are not allowed as trusted artifact roots: $Path"
    }
    $root = (Resolve-Path -LiteralPath $Path).Path.TrimEnd("\")
    $items = @(Get-ChildItem -LiteralPath $root -Force -Recurse)
    $reparsePoints = @($items | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    })
    if ($reparsePoints.Count -gt 0) {
        throw "Reparse points are not allowed in trusted artifact trees: $($reparsePoints[0].FullName)"
    }

    $entries = @($items | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
        $relative = $_.FullName.Substring($root.Length + 1).Replace("\", "/").ToLowerInvariant()
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        $relative + [char]0 + $hash
    })
    [Array]::Sort($entries, [StringComparer]::Ordinal)
    $payload = [Text.Encoding]::UTF8.GetBytes(($entries -join "`n") + "`n")
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($payload))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Assert-DirectoryTreeSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [string]$Label = "directory"
    )

    $actual = Get-DirectoryTreeSha256 -Path $Path
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "$Label failed tree SHA-256 verification: $Path (expected $ExpectedSha256, got $actual)"
    }
}

function Assert-AuthenticodeSigner {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$SubjectContains,
        [string]$Label = "executable"
    )

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    $subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" }
    if ($signature.Status -ne "Valid" -or $subject -notlike "*$SubjectContains*") {
        throw "$Label has an untrusted Authenticode signature: $Path (status=$($signature.Status), signer=$subject)"
    }
}

function Assert-NoReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Label = "path")

    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "$Label contains a reparse point: $current"
            }
        }
        $parent = Split-Path -Parent $current
        if (-not $parent -or $parent -eq $current) {
            break
        }
        $current = $parent
    }
}

function Resolve-TrustedExecutable {
    param(
        [Parameter(Mandatory = $true)][string[]]$CandidatePaths,
        [Parameter(Mandatory = $true)][string]$SignerSubjectContains,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($candidate in $CandidatePaths) {
        $expanded = [Environment]::ExpandEnvironmentVariables($candidate)
        if (Test-Path -LiteralPath $expanded -PathType Leaf) {
            Assert-NoReparsePoint -Path $expanded -Label $Label
            $resolved = (Resolve-Path -LiteralPath $expanded).Path
            Assert-AuthenticodeSigner -Path $resolved -SubjectContains $SignerSubjectContains -Label $Label
            return $resolved
        }
    }
    throw "$Label was not found in an approved location. Checked: $($CandidatePaths -join ', ')"
}

