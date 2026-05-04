$ErrorActionPreference = "Stop"

$Keys = @(
    "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1",
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
