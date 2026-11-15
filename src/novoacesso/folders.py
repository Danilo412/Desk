"""Bounded folder packages. Never follow links or overwrite an extracted folder."""
from pathlib import Path,PurePosixPath
import os,re,shutil,stat,tempfile,zipfile

MAX_BYTES=250*1024*1024
MAX_ENTRIES=5000
RESERVED={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

def _parts(name):
    parts=PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or len(name)>220:raise ValueError('Caminho inválido no pacote de pasta.')
    for part in parts:
        if part in ('.','..') or part.rstrip(' .')!=part or any(c in part for c in ':\x00<>"|?*') or part.split('.')[0].upper() in RESERVED:
            raise ValueError('Nome de arquivo incompatível ou caminho inseguro no pacote.')
    return parts

def pack_folder(folder,archive,cancelled=lambda:False):
    folder=Path(folder).resolve(strict=True);archive=Path(archive)
    if not folder.is_dir():raise ValueError('Selecione uma pasta.')
    _parts(folder.name);count=0;total=0
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as output:
        for current,dirs,files in os.walk(folder,followlinks=False):
            if cancelled():raise InterruptedError('Envio da pasta cancelado.')
            current=Path(current)
            for name in [*dirs,*files]:
                child=current/name
                if child.is_symlink() or (hasattr(child,'is_junction') and child.is_junction()):raise ValueError('A pasta contém links ou junções. Remova esses itens do pacote antes de enviar.')
            relative=PurePosixPath(folder.name)/(current.relative_to(folder).as_posix() if current!=folder else '')
            _parts(str(relative));output.writestr(str(relative).rstrip('/')+'/',b'');count+=1
            for name in files:
                if cancelled():raise InterruptedError('Envio da pasta cancelado.')
                path=current/name
                if not path.resolve().is_relative_to(folder):raise ValueError('Arquivo fora da pasta selecionada.')
                arcname=str(relative/name);_parts(arcname);total+=path.stat().st_size;count+=1
                if total>MAX_BYTES or count>MAX_ENTRIES:raise ValueError('O limite da pasta é 250 MB e 5.000 itens.')
                entry=zipfile.ZipInfo.from_file(path,arcname,strict_timestamps=False);entry.compress_type=zipfile.ZIP_DEFLATED
                with path.open('rb') as incoming,output.open(entry,'w') as outgoing:
                    while chunk:=incoming.read(65536):
                        if cancelled():raise InterruptedError('Envio da pasta cancelado.')
                        outgoing.write(chunk)
            if count>MAX_ENTRIES:raise ValueError('O limite da pasta é 5.000 itens.')
    if archive.stat().st_size>MAX_BYTES:raise ValueError('O pacote compactado ultrapassou 250 MB.')
    return dict(files=count,bytes=total)

def extract_folder(archive,parent):
    parent=Path(parent).resolve(strict=True)
    if not parent.is_dir():raise ValueError('Escolha uma pasta de destino.')
    with zipfile.ZipFile(archive) as source:
        entries=source.infolist();seen=set();total=0;roots=set()
        if not entries or len(entries)>MAX_ENTRIES:raise ValueError('Quantidade de itens inválida no pacote.')
        for entry in entries:
            parts=_parts(entry.filename);roots.add(parts[0]);key='/'.join(parts).casefold()
            if key in seen:raise ValueError('Nomes duplicados no pacote.')
            seen.add(key);mode=(entry.external_attr>>16)&0xffff
            if stat.S_IFMT(mode)==stat.S_IFLNK or entry.flag_bits&1 or entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('Links, criptografia ou compressão não suportada no pacote.')
            total+=entry.file_size
            if total>MAX_BYTES:raise ValueError('A pasta expandida ultrapassa 250 MB.')
        if len(roots)!=1 or not any(len(_parts(e.filename))>1 or e.is_dir() for e in entries):raise ValueError('O pacote deve conter uma única pasta raiz.')
        root=next(iter(roots));destination=parent/root
        for index in range(2,10000):
            if not destination.exists():break
            destination=parent/f'{root} ({index})'
        else:raise ValueError('Não foi possível escolher um nome livre para a pasta.')
        with tempfile.TemporaryDirectory(prefix='.desk-folder-',dir=parent) as temporary:
            staging=Path(temporary).resolve()
            for entry in entries:
                target=staging.joinpath(*_parts(entry.filename))
                if not target.resolve().is_relative_to(staging):raise ValueError('Caminho fora do destino da pasta.')
                if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.open(entry) as incoming,target.open('xb') as outgoing:
                    remaining=entry.file_size
                    while chunk:=incoming.read(min(65536,remaining+1)):
                        remaining-=len(chunk)
                        if remaining<0:raise ValueError('Tamanho expandido incorreto.')
                        outgoing.write(chunk)
                    if remaining:raise ValueError('Arquivo incompleto no pacote.')
            (staging/root).rename(destination)
    return destination
