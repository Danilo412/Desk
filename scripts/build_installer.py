from pathlib import Path
import urllib.request,hashlib,subprocess,os,json
root=Path(__file__).resolve().parents[1];tools=root/'.tools';tools.mkdir(exist_ok=True)
setup=tools/'innosetup-7.1.1-x64.exe';compiler=tools/'InnoSetup/ISCC.exe'
url='https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
expected='8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'
if not setup.exists():
    with urllib.request.urlopen(url,timeout=60) as response,setup.open('wb') as out:out.write(response.read())
assert hashlib.sha256(setup.read_bytes()).hexdigest()==expected,'Compiler download hash mismatch'
env=os.environ.copy();env['DESK_COMPILER_EXE']=str(setup)
verify="$sig = Get-AuthenticodeSignature -LiteralPath $env:DESK_COMPILER_EXE; if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike '*Pyrsys*') { exit 1 }; Write-Output 'Compiler Authenticode verified'"
powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',verify],env=env,check=True)
if not compiler.exists():subprocess.run([str(setup),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/NOICONS','/DIR='+str(compiler.parent)],check=True)
assert not (root/'dist/Desk/internet.json').exists(),'Refusing to publish connection credentials'
subprocess.run([str(compiler),str(root/'packaging/Desk.iss')],cwd=root,check=True)
publish=root/'dist/publish'
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(publish.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'}
(publish/'SHA256SUMS.txt').write_text(''.join(value+'  '+name+'\n' for name,value in manifest.items()),encoding='utf-8')
print(json.dumps(dict(installer_built=True,unsigned=True,live_credentials_included=False)))
