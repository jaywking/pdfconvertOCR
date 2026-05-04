#define MyAppName "PDFConvertOCR"
#ifndef MyAppVersion
#define MyAppVersion "6.1.1"
#endif
#define MyAppPublisher "jaywking"
#define MyAppExeName "run_single_pdf.bat"

[Setup]
AppId={{8F09513D-B90D-4E0B-986E-80E4530D54DF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\PDFConvertOCR
DefaultGroupName=PDFConvertOCR
DisableProgramGroupPage=yes
OutputBaseFilename=PDFConvertOCR-Setup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=PDFConvertOCR
SetupLogging=yes
InfoAfterFile=INSTALL_COMPLETE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Setup has finished installing [name]. To use it, right-click a PDF in File Explorer and choose "Convert to OCR (v6.1)".
FinishedLabelNoIcons=Setup has finished installing [name]. To use it, right-click a PDF in File Explorer and choose "Convert to OCR (v6.1)".

[Files]
Source: "..\pdf_automation_v6.1.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\run_single_pdf.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup_installed_app.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\RIGHT_CLICK_CONTEXT_MENU.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\HOW_TO_USE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "vendor\python\*"; DestDir: "{app}\vendor\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\wheelhouse\*"; DestDir: "{app}\vendor\wheelhouse"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\ghostscript\*"; DestDir: "{app}\vendor\ghostscript"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\tesseract\*"; DestDir: "{app}\vendor\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\pngquant\*"; DestDir: "{app}\vendor\pngquant"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1"; ValueType: string; ValueData: "Convert to OCR (v6.1)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1"; ValueType: string; ValueName: "Icon"; ValueData: "{sys}\imageres.dll,-5302"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Document"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1\command"; ValueType: string; ValueData: """{app}\run_single_pdf.bat"" ""%L"""; Flags: uninsdeletekey

[Icons]
Name: "{group}\PDFConvertOCR install folder"; Filename: "{app}"
Name: "{group}\How to use PDFConvertOCR"; Filename: "notepad.exe"; Parameters: """{app}\HOW_TO_USE.txt"""
Name: "{group}\Uninstall PDFConvertOCR"; Filename: "{uninstallexe}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_installed_app.ps1"""; StatusMsg: "Preparing the PDFConvertOCR offline runtime..."; Flags: runhidden waituntilterminated
Filename: "notepad.exe"; Parameters: """{app}\HOW_TO_USE.txt"""; Description: "Open quick instructions"; Flags: postinstall skipifsilent nowait unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\vendor"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}\_complete"
Type: dirifempty; Name: "{app}\_processed"
Type: dirifempty; Name: "{app}"
