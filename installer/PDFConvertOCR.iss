#ifndef MyAppName
#define MyAppName "PDFConvertOCR"
#endif
#ifndef MyAppVersion
#define MyAppVersion "6.2.0"
#endif
#ifndef MyDisplayVersion
#define MyDisplayVersion "6.2"
#endif
#ifndef MyMenuLabel
#define MyMenuLabel "Convert to OCR (v6.2)"
#endif
#ifndef MyContextVerb
#define MyContextVerb "ConvertToOCRv6.2"
#endif
#ifndef MyAppPublisher
#define MyAppPublisher "jaywking"
#endif
#ifndef MyMainScript
#define MyMainScript "pdf_automation_v6.2.py"
#endif
#ifndef MyRunnerScript
#define MyRunnerScript "run_single_pdf.bat"
#endif
#ifndef MySetupBaseName
#define MySetupBaseName "PDFConvertOCR-Setup-v"
#endif

[Setup]
AppId={{8F09513D-B90D-4E0B-986E-80E4530D54DF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename={#MySetupBaseName}{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
SetupLogging=yes
InfoAfterFile=INSTALL_COMPLETE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Setup has finished installing [name]. To use it, right-click a PDF in File Explorer and choose "{#MyMenuLabel}".
FinishedLabelNoIcons=Setup has finished installing [name]. To use it, right-click a PDF in File Explorer and choose "{#MyMenuLabel}".

[Files]
Source: "..\{#MyMainScript}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\{#MyRunnerScript}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app_metadata.json"; DestDir: "{app}"; Flags: ignoreversion
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
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\{#MyContextVerb}"; ValueType: string; ValueData: "{#MyMenuLabel}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\{#MyContextVerb}"; ValueType: string; ValueName: "Icon"; ValueData: "{sys}\imageres.dll,-5302"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\{#MyContextVerb}"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Document"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\{#MyContextVerb}\command"; ValueType: string; ValueData: """{app}\{#MyRunnerScript}"" ""%L"""; Flags: uninsdeletekey

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { Prevent a v6.1-to-v6.2 upgrade from leaving two Explorer menu entries. }
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\SystemFileAssociations\.pdf\shell\ConvertToOCRv6.1');
  end;
end;

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
