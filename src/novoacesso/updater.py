"""Public, authenticated updates. Never accepts instructions from a peer.

An Ed25519 manifest authenticates the publisher and SHA-256 authenticates the
installer bytes. This is separate from Windows Authenticode: Windows still
applies its own signature and application-control policy to the installer.
"""
from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import secrets
import urllib.error
import urllib.parse
import urllib.request
from .update_trust import UPDATE_PUBLIC_KEY

REPOSITORY='Danilo412/Desk'
MANIFEST_URL=f'https://github.com/{REPOSITORY}/releases/latest/download/desk-update.json'
MAX_INSTALLER=200*1024*1024
MAX_MANIFEST=64*1024
APP_ID='{118A8B81-6561-4B50-88C6-E4E569DC6909}'

class UpdateError(ValueError):pass

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})',value):
        raise UpdateError('Versão da atualização inválida.')
    return tuple(map(int,value.split('.')))

def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

@dataclass(frozen=True)
class Update:
    version:str
    url:str
    sha256:str
    size:int
    notes:str

def verify_manifest(data,current_version,public_key=UPDATE_PUBLIC_KEY):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        if len(data)>MAX_MANIFEST:raise UpdateError('Aviso de atualização muito grande.')
        envelope=json.loads(data)
        if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:raise UpdateError('Aviso de atualização inválido.')
        payload=envelope['payload']
        if not isinstance(payload,dict) or set(payload)!={'schema','version','platform','url','sha256','size','notes'}:raise UpdateError('Conteúdo da atualização inválido.')
        signature=base64.b64decode(envelope['signature'],validate=True)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature,canonical(payload))
        version=payload['version'];version_tuple(version)
        if type(payload['schema']) is not int or payload['schema']!=1 or payload['platform']!='windows-x64':raise UpdateError('Atualização incompatível com este Desk.')
        expected=f'https://github.com/{REPOSITORY}/releases/download/v{version}/Desk-{version}-Update.exe'
        if payload['url']!=expected:raise UpdateError('Endereço de atualização não autorizado.')
        if not isinstance(payload['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',payload['sha256']):raise UpdateError('Conferência do instalador inválida.')
        if type(payload['size']) is not int or not 1024<=payload['size']<=MAX_INSTALLER:raise UpdateError('Tamanho do instalador inválido.')
        if not isinstance(payload['notes'],str) or len(payload['notes'])>8000:raise UpdateError('Descrição da atualização inválida.')
        if version_tuple(version)<=version_tuple(current_version):return None
        return Update(version,payload['url'],payload['sha256'],payload['size'],payload['notes'])
    except UpdateError:raise
    except Exception as error:raise UpdateError('A origem da atualização não pôde ser confirmada.') from error

def _allowed_transport(url):
    p=urllib.parse.urlsplit(url)
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and p.hostname in {
        'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','github-releases.githubusercontent.com'}

class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not _allowed_transport(newurl):raise UpdateError('Redirecionamento de atualização não autorizado.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def _open(url):
    if not _allowed_transport(url):raise UpdateError('Endereço de atualização não autorizado.')
    request=urllib.request.Request(url,headers={'User-Agent':'Desk-Updater','Cache-Control':'no-cache'})
    return urllib.request.build_opener(_Redirects()).open(request,timeout=20)

def check_update(current_version,opener=None):
    if opener is None:opener=_open
    try:
        # GitHub's latest redirect can briefly retain the preceding release
        # after publication. A fresh query avoids reporting that stale result.
        with opener(MANIFEST_URL+'?desk_check='+secrets.token_hex(8)) as response:data=response.read(MAX_MANIFEST+1)
        return verify_manifest(data,current_version)
    except urllib.error.HTTPError as error:
        if error.code==404:raise UpdateError('O aviso de atualização ainda não está disponível no canal oficial. Tente novamente ou abra a página de versões.') from error
        raise UpdateError('Não foi possível consultar as atualizações agora.') from error
    except UpdateError:raise
    except Exception as error:raise UpdateError('Sem resposta do serviço de atualização. Tente novamente mais tarde.') from error

def _file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()

def verify_installer_file(path,update):
    target=Path(path)
    if not target.is_file():return False
    try:
        return target.stat().st_size==update.size and _file_sha256(target)==update.sha256
    except OSError:
        return False

def cached_filename(update):
    version_tuple(update.version)
    return f'Desk-{update.version}-Update.exe'

def cached_update_path(update,cache):
    try:target=Path(cache)/cached_filename(update)
    except UpdateError:return None
    return target if verify_installer_file(target,update) else None

def promote_cached_update(update,path,cache):
    source=Path(path)
    target=Path(cache)/cached_filename(update)
    if source.resolve()==target.resolve():return target
    try:
        source.replace(target)
        return target
    except OSError:
        return source

def cleanup_old_downloads(cache,keep_path=None):
    folder=Path(cache)
    if not folder.is_dir():return
    keep=Path(keep_path).resolve() if keep_path else None
    for entry in folder.iterdir():
        try:
            if not entry.is_file():continue
            if keep is not None and entry.resolve()==keep:continue
            name=entry.name
            if name.startswith('desk-update-') and name.endswith(('.part','.exe')):
                entry.unlink(missing_ok=True)
            elif name.startswith('Desk-') and name.endswith('-Update.exe'):
                entry.unlink(missing_ok=True)
        except OSError:
            pass

def download_update(update,cache,progress=lambda received,total:None,cancel=None,opener=None):
    if opener is None:opener=_open
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='desk-update-',suffix='.part',dir=cache)
    temporary=Path(name);target=temporary.with_suffix('.exe')
    try:
        digest=hashlib.sha256();received=0
        with os.fdopen(fd,'wb') as destination,opener(update.url) as response:
            while True:
                if cancel is not None and cancel.is_set():raise UpdateError('Download cancelado.')
                chunk=response.read(128*1024)
                if not chunk:break
                received+=len(chunk)
                if received>update.size:raise UpdateError('O tamanho do instalador não confere.')
                destination.write(chunk);digest.update(chunk);progress(received,update.size)
            destination.flush();os.fsync(destination.fileno())
        if received!=update.size or digest.hexdigest()!=update.sha256:raise UpdateError('O instalador não passou na conferência. Nenhum arquivo foi instalado.')
        if os.name=='nt':
            # Retain Windows' normal Internet-origin checks for the download.
            Path(str(temporary)+':Zone.Identifier').write_text('[ZoneTransfer]\nZoneId=3\nHostUrl='+update.url+'\n',encoding='utf-8')
        temporary.replace(target)
        return target
    except Exception:
        temporary.unlink(missing_ok=True);raise

def installed_directory():
    """Only an actual per-user installation may install an in-place update."""
    if os.name!='nt' or not getattr(sys,'frozen',False):return None
    import ctypes,winreg
    try:
        length=ctypes.c_uint32()
        if ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length),None)!=15700:return None
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,rf'Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1') as key:
            location=Path(winreg.QueryValueEx(key,'InstallLocation')[0]).resolve()
        executable=Path(sys.executable).resolve()
        return location if executable.name.lower()=='desk.exe' and executable.parent==location else None
    except (OSError,ValueError,AttributeError):return None

def launch_installer(path,update,installation,runner=subprocess.Popen):
    """Called only after the local user's explicit click and idle-session check.

    Recheck downloaded bytes immediately before starting. No shell, quiet
    installation, forced application close, reboot, or protection override.
    """
    path=Path(path).resolve();installation=Path(installation).resolve()
    if path.stat().st_size!=update.size or _file_sha256(path)!=update.sha256:
        raise UpdateError('O instalador foi alterado depois do download. Baixe novamente.')
    return runner([str(path),'/DIR='+str(installation),'/NORESTART','/NOCLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS'],cwd=installation)
