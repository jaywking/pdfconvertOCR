$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$MetadataPath = Join-Path $ProjectRoot "app_metadata.json"
if (-not (Test-Path $MetadataPath)) {
    throw "Missing app_metadata.json at $MetadataPath"
}
$Metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json

$Keys = @(
    "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\$($Metadata.contextVerb)",
    "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\PDFConvertV6"
)

foreach ($Key in $Keys) {
    if (Test-Path $Key) {
        Remove-Item -Path $Key -Recurse -Force
        Write-Host "Removed $Key"
    } else {
        Write-Host "Not present: $Key"
    }
}

Write-Host ""
Write-Host "If Explorer still shows the menu item, restart Explorer or sign out and back in."
