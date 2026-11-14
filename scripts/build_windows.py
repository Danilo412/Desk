from pathlib import Path
import sys,subprocess,shutil,zipfile,json,hashlib
root=Path(__file__).resolve().parents[1];target=root/'dist/Desk';publish=root/'dist/publish'
assert target.resolve().is_relative_to(root.resolve())
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(root/'dist'),'--workpath',str(root/'build'),str(root/'packaging/Desk.spec')],cwd=root,check=True)
for name in ('assets','licencas'):shutil.copytree(root/name,target/name,dirs_exist_ok=True)
for name in ('LICENSE','internet.example.json'):shutil.copy2(root/name,target/name)
shutil.copy2(root/'packaging/README_INSTALL.txt',target/'COMO-USAR.txt')
assert not (target/'internet.json').exists(),'Public build must not contain a real connection configuration'
publish.mkdir(parents=True,exist_ok=True)
tracked=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True).stdout.decode().split('\0')
with zipfile.ZipFile(target/'codigo-fonte-Desk-0.9.9.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(filter(None,tracked)):
        path=root/name
        if path.is_file():archive.write(path,'Desk/'+name)
shutil.copy2(target/'codigo-fonte-Desk-0.9.9.zip',publish/'Desk-0.9.9-Codigo-Fonte.zip')
files=[p for p in target.rglob('*') if p.is_file()]
assert not any(p.name in ('identity.dat','internet.json') for p in files)
print(json.dumps(dict(public_build=True,files=len(files),live_connection_configuration=False)))
