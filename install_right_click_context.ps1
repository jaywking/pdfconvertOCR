$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunSinglePdfBat = Join-Path $ProjectRoot "run_single_pdf.bat"
$BootstrapScript = Join-Path $ProjectRoot "bootstrap.ps1"
$MainScript = Join-Path $ProjectRoot "pdf_automation_v6.1.py"

if (-not (Test-Path $RunSinglePdfBat)) {
    throw "Missing run_single_pdf.bat at $RunSinglePdfBat"
}

if (-not (Test-Path $BootstrapScript)) {
    throw "Missing bootstrap.ps1 at $BootstrapScript"
}

if (-not (Test-Path $MainScript)) {
    throw "Missing pdf_automation_v6.1.py at $MainScript"
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Preparing Python environment..."
& $BootstrapScript

$VerbKey = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1"
$CommandKey = Join-Path $VerbKey "command"
$MenuLabel = "Convert to OCR (v6.1)"
$Icon = "C:\Windows\System32\imageres.dll,-5302"
$Command = ('"{0}" "%L"' -f $RunSinglePdfBat)

Write-Host "Creating Explorer right-click menu entry..."
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
