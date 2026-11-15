from pathlib import Path
import subprocess,hashlib,json
root=Path(__file__).resolve().parents[1]
subprocess.run([str(root/'.tools/InnoSetup/ISCC.exe'),'/O'+str(root/'dist/publish'),str(root/'native/DeskHost/DeskHost.iss')],check=True)
publish=root/'dist/publish'
(publish/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(publish.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='ascii')
print(json.dumps(dict(service_installer_built=True,service_installed=False,production_activation_requires_signing=True)))
