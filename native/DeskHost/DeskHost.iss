#define BrokerRoot SourcePath + "bin"
[Setup]
AppId={{B6439583-F688-498A-A469-75DA14DBD88B}
AppName=Desk - Serviço de tela de bloqueio
AppVersion=0.13.0
VersionInfoVersion=0.13.0.0
AppPublisher=Desk
DefaultDirName={autopf}\DeskHost
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\..\Desk-Servico-0.13.0-Preparacao
OutputBaseFilename=Desk-Service-0.13.0-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
SignedUninstaller=no
LicenseFile=..\..\LICENSE

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#BrokerRoot}\DeskHost.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BrokerRoot}\DeskHost.exe"; DestDir: "{tmp}"; DestName: "DeskHost-Verify.exe"; Flags: dontcopy

[UninstallRun]
Filename: "{app}\DeskHost.exe"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated

[Code]
var ClientPage: TInputFileWizardPage;
procedure InitializeWizard;
begin
  ClientPage := CreateInputFilePage(wpWelcome, 'Desk que poderá usar o serviço',
    'Selecione o Desk assinado instalado para o usuário que receberá o acesso.',
    'O serviço permite ver e controlar a tela bloqueada durante sessões autorizadas. ' +
    'Não inicia uma sessão remota sozinho e não armazena a senha do Windows. ' +
    'Esta preparação só instala se o serviço e o Desk tiverem assinaturas confiáveis do mesmo editor.');
  ClientPage.Add('Aplicativo Desk:', 'Desk|Desk.exe', '.exe');
  ClientPage.Values[0] := ExpandConstant('{localappdata}\Programs\Desk\Desk.exe');
end;
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ClientPage.ID then begin
    Result := FileExists(ClientPage.Values[0]);
    if not Result then MsgBox('Selecione o Desk.exe instalado para o usuário autorizado.', mbError, MB_OK);
  end;
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if CompareText(RemoveBackslashUnlessRoot(ExpandFileName(WizardDirValue)), ExpandConstant('{autopf}\DeskHost')) <> 0 then begin
    Result := 'O serviço exige a pasta protegida padrão em Arquivos de Programas.';
    Exit;
  end;
  if RegKeyExists(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Services\DeskScreenBroker') then begin
    Result := 'O serviço já está instalado. Remova a instalação anterior pelo Windows antes de instalar esta preparação.';
    Exit;
  end;
  ExtractTemporaryFile('DeskHost-Verify.exe');
  if not Exec(ExpandConstant('{tmp}\DeskHost-Verify.exe'),
    '--preflight "' + ClientPage.Values[0] + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := 'O Windows não permitiu verificar a assinatura. O serviço não foi instalado.'
  else if ExitCode <> 0 then
    Result := 'Falta uma assinatura digital confiável e correspondente no serviço e no Desk. ' +
      'Este pacote de preparação não ativa um serviço sem assinatura. Nada foi registrado no Windows.';
end;
procedure CurStepChanged(CurStep: TSetupStep);
var ExitCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{app}\DeskHost.exe'),
      '--install-client "' + ClientPage.Values[0] + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      RaiseException('O Windows recusou o serviço. A instalação não está ativa.')
    else if ExitCode <> 0 then
      RaiseException('O serviço não foi autorizado ou não iniciou. Confira a assinatura e a conta proprietária do Desk.');
  end;
end;
