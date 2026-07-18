$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$MetadataPath = Join-Path $ProjectRoot "app_metadata.json"
if (-not (Test-Path $MetadataPath)) {
    throw "Missing app_metadata.json at $MetadataPath"
}
$Metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json

$RunSinglePdfBat = Join-Path $ProjectRoot $Metadata.runnerScript
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$MainScript = Join-Path $ProjectRoot $Metadata.mainScript

if (-not (Test-Path $RunSinglePdfBat)) {
    throw "Missing $($Metadata.runnerScript) at $RunSinglePdfBat"
}

if (-not (Test-Path $BootstrapScript)) {
    throw "Missing bootstrap.ps1 at $BootstrapScript"
}

if (-not (Test-Path $MainScript)) {
    throw "Missing $($Metadata.mainScript) at $MainScript"
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Preparing Python environment..."
& $BootstrapScript

$VerbKey = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\$($Metadata.contextVerb)"
$LegacyVerbKey = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1"
$CommandKey = Join-Path $VerbKey "command"
$MenuLabel = $Metadata.menuLabel
$Icon = "C:\Windows\System32\imageres.dll,-5302"
$Command = ('"{0}" "%L"' -f $RunSinglePdfBat)

Write-Host "Creating Explorer right-click menu entry..."
if ($LegacyVerbKey -ne $VerbKey -and (Test-Path -LiteralPath $LegacyVerbKey)) {
    Remove-Item -LiteralPath $LegacyVerbKey -Recurse -Force
}
New-Item -Path $VerbKey -Force | Out-Null
Set-Item -Path $VerbKey -Value $MenuLabel
New-ItemProperty -Path $VerbKey -Name "Icon" -Value $Icon -PropertyType String -Force | Out-Null
New-ItemProperty -Path $VerbKey -Name "MultiSelectModel" -Value "Document" -PropertyType String -Force | Out-Null

New-Item -Path $CommandKey -Force | Out-Null
Set-Item -Path $CommandKey -Value $Command

Write-Host ""
Write-Host "Installed: $MenuLabel"
Write-Host "Registry key: $VerbKey"
Write-Host "Command: $Command"
Write-Host ""
Write-Host "Try it by right-clicking a PDF in Explorer and choosing '$MenuLabel'."
