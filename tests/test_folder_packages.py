from pathlib import Path
import zipfile,stat
import pytest
from novoacesso.folders import pack_folder,extract_folder

def test_folder_round_trip_and_existing_folder_preserved(tmp_path):
    folder=tmp_path/'origem';(folder/'sub').mkdir(parents=True);(folder/'sub/ação.txt').write_text('conteúdo',encoding='utf-8');(folder/'vazia').mkdir()
    package=tmp_path/'pasta.zip';pack_folder(folder,package)
    destination=tmp_path/'recebidas';destination.mkdir();(destination/'origem').mkdir();(destination/'origem/antigo.txt').write_text('manter')
    result=extract_folder(package,destination)
    assert result.name=='origem (2)' and (result/'sub/ação.txt').read_text(encoding='utf-8')=='conteúdo' and (result/'vazia').is_dir()
    assert (destination/'origem/antigo.txt').read_text()=='manter'

@pytest.mark.parametrize('name',['../escape.txt','/absolute.txt','pasta/../escape.txt','pasta/C:stream','pasta/NUL.txt','pasta/trailing.','pasta\\..\\escape.txt'])
def test_unsafe_zip_paths_are_refused_without_writing(tmp_path,name):
    archive=tmp_path/'bad.zip';destination=tmp_path/'out';destination.mkdir()
    with zipfile.ZipFile(archive,'w') as output:output.writestr(name,b'bad')
    with pytest.raises(ValueError):extract_folder(archive,destination)
    assert not list(destination.iterdir())

def test_symlinks_duplicates_and_expanded_size_limit(tmp_path,monkeypatch):
    from novoacesso import folders
    out=tmp_path/'out';out.mkdir();archive=tmp_path/'link.zip'
    entry=zipfile.ZipInfo('folder/link');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(archive,'w') as output:output.writestr(entry,b'/outside')
    with pytest.raises(ValueError):extract_folder(archive,out)
    archive=tmp_path/'case.zip'
    with zipfile.ZipFile(archive,'w') as output:output.writestr('folder/Test.txt',b'a');output.writestr('folder/test.txt',b'b')
    with pytest.raises(ValueError):extract_folder(archive,out)
    monkeypatch.setattr(folders,'MAX_BYTES',16);archive=tmp_path/'large.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:output.writestr('folder/file.txt',b'a'*17)
    with pytest.raises(ValueError):extract_folder(archive,out)
    assert not list(out.iterdir())
