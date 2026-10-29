#ifndef SourceRoot
  #error SourceRoot must point to the verified portable build
#endif
#ifndef ReleaseOutput
  #define ReleaseOutput "..\delivery\setup-v0.1.1"
#endif

[Setup]
AppId={{529AACBE-D7AB-4DE1-8E24-2D58BFA3B78C}
AppName=모아컷
AppVersion=0.1.1
AppPublisher=MOACUT
DefaultDirName={localappdata}\Programs\MOACUT
DefaultGroupName=모아컷
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableWelcomePage=no
ShowLanguageDialog=no
Compression=lzma2/ultra64
SolidCompression=yes
LZMADictionarySize=262144
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
OutputDir={#ReleaseOutput}
OutputBaseFilename=MOACUT-Setup-0.1.1-Windows-x64
UninstallDisplayIcon={app}\MOACUT.exe
UninstallDisplayName=모아컷
UninstallFilesDir={app}\uninstall
AppMutex=Local\MOACUT_MVP
SetupMutex=MOACUTSetupSingle
CloseApplications=no
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\모아컷"; Filename: "{app}\MOACUT.exe"
Name: "{group}\모아컷"; Filename: "{app}\MOACUT.exe"
Name: "{group}\사용 안내"; Filename: "{app}\사용안내.md"

[Run]
Filename: "{app}\MOACUT.exe"; Description: "모아컷 실행"; Flags: nowait postinstall skipifsilent

; User photographs and jobs live in LOCALAPPDATA\MOACUT, outside {app}.
; Deliberately no UninstallDelete entry: uninstall must preserve those files.
