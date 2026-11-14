#define AppRoot SourcePath + "..\dist\Desk"
[Setup]
AppId={{118A8B81-6561-4B50-88C6-E4E569DC6909}
AppName=Desk
AppVersion=0.9.9
VersionInfoVersion=0.9.9.0
AppPublisher=Desk
DefaultDirName={localappdata}\Programs\Desk
DefaultGroupName=Desk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\publish
OutputBaseFilename=Desk-0.9.9-Publico-Setup
SetupIconFile=..\assets\desk.ico
UninstallDisplayIcon={app}\Desk.exe
LicenseFile=..\LICENSE
InfoAfterFile=README_INSTALL.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
SignedUninstaller=no
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Tasks]
Name: "desktopicon"; Description: "Criar um atalho do Desk na Área de Trabalho"; GroupDescription: "Atalhos:"
[Files]
Source: "{#AppRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Desk"; Filename: "{app}\Desk.exe"; WorkingDir: "{app}"
Name: "{group}\Como usar o Desk"; Filename: "{app}\COMO-USAR.txt"
Name: "{autodesktop}\Desk"; Filename: "{app}\Desk.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\Desk.exe"; Description: "Abrir o Desk"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
