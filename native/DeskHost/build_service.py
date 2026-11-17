"""Compile/test without installing a service or touching an interactive desktop."""
from pathlib import Path
import os,subprocess,json,hashlib,shutil
root=Path(__file__).resolve().parents[2];source=Path(__file__).resolve().parent
framework=Path(os.environ['SystemRoot'])/'Microsoft.NET/Framework64/v4.0.30319';out=source/'bin';out.mkdir(exist_ok=True)
binary=out/'DeskHost.exe'
subprocess.run([str(framework/'csc.exe'),'/nologo','/platform:x64','/target:exe','/optimize+','/debug-','/out:'+str(binary),'/reference:'+str(framework/'System.ServiceProcess.dll'),'/reference:'+str(framework/'System.Runtime.Serialization.dll'),str(source/'DeskHost.cs')],check=True)
p=subprocess.run([str(binary),'--self-test'],capture_output=True,text=True,timeout=15,check=True)
pure=json.loads(p.stdout);assert pure['passed'] and pure['privileged_actions'] is False
# Unsigned production preflight must fail. No SCM/desktop operation is in
# this branch; it checks Authenticode before returning an authorization.
refusal=subprocess.run([str(binary),'--preflight',str(binary)],capture_output=True,text=True,timeout=30)
assert refusal.returncode==20,'Unsigned native component unexpectedly authorized'
publish=root/'dist/publish';publish.mkdir(parents=True,exist_ok=True);shutil.copy2(binary,publish/'DeskHost-0.14.1-Unsigned.exe')
report=dict(passed=True,framing=pure,unsigned_preflight_refused=True,service_installed=False,privileged_actions=False,sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
(publish/'service-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
