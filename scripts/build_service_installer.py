from pathlib import Path
import subprocess,hashlib,json
root=Path(__file__).resolve().parents[1];native=root/'native/DeskHost';publish=root/'dist/publish'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
service=native/'bin/DeskHost.exe';client=root/'dist/Desk/Desk.exe'
service_hash=sha(service);client_hash=sha(client)
(native/'build-hashes.iss').write_text('#define ServiceExpectedHash "'+service_hash+'"\n#define ClientExpectedHash "'+client_hash+'"\n',encoding='ascii')
good=subprocess.run([str(service),'--preflight-fixed',service_hash,client_hash,str(client)],capture_output=True,timeout=30)
bad=subprocess.run([str(service),'--preflight-fixed',service_hash,'0'*64,str(client)],capture_output=True,timeout=30)
assert good.returncode==0 and bad.returncode==20
subprocess.run([str(root/'.tools/InnoSetup/ISCC.exe'),'/O'+str(publish),str(native/'DeskHost.iss')],check=True)
(publish/'fixed-version-validation.json').write_text(json.dumps(dict(passed=True,exact_versions_accepted=True,wrong_version_refused=True,service_installed=False,service_sha256=service_hash,client_sha256=client_hash),indent=2),encoding='utf-8')
(publish/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(publish.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='ascii')
print(json.dumps(dict(service_installer_built=True,service_installed=False,administrative_approval_required=True,windows_policy_modified=False)))
