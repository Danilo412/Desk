import base64,hashlib,io,json,threading
from types import SimpleNamespace
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from novoacesso import updater

@pytest.fixture
def signed():
    key=Ed25519PrivateKey.generate();body=b'MZ'+b'installer-fixture'*100
    payload=dict(schema=1,version='0.12.1',platform='windows-x64',url='https://github.com/Danilo412/Desk/releases/download/v0.12.1/Desk-0.12.1-Update.exe',sha256=hashlib.sha256(body).hexdigest(),size=len(body),notes='Correções de conexão.')
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
    def encode(p=payload):return json.dumps(dict(payload=p,signature=base64.b64encode(key.sign(updater.canonical(p))).decode())).encode()
    return payload,body,public,encode

def test_update_signature_and_rollback_protection(signed):
    payload,body,public,encode=signed
    assert updater.verify_manifest(encode(),'0.12.0',public).version=='0.12.1'
    assert updater.verify_manifest(encode(),'0.12.1',public) is None
    assert updater.verify_manifest(encode(),'0.13.0',public) is None
    changed=json.loads(encode());changed['payload']['notes']='substituído'
    with pytest.raises(updater.UpdateError):updater.verify_manifest(json.dumps(changed).encode(),'0.12.0',public)
    other=Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
    with pytest.raises(updater.UpdateError):updater.verify_manifest(encode(),'0.12.0',other)

@pytest.mark.parametrize('change',[
    {'url':'https://example.com/Desk.exe'},
    {'url':'https://github.com/Other/Desk/releases/download/v0.12.1/Desk-0.12.1-Update.exe'},
    {'url':'file:///C:/Desk.exe'},
    {'version':'0.12.1/../../evil'},
    {'version':'01.12.1'},
    {'platform':'linux-x64'},
    {'size':True},
    {'size':updater.MAX_INSTALLER+1},
    {'sha256':'a'*63},
])
def test_even_signed_manifest_rejects_wrong_platform_paths_and_sizes(signed,change):
    payload,body,public,encode=signed
    with pytest.raises(updater.UpdateError):updater.verify_manifest(encode(dict(payload,**change)),'0.12.0',public)

def test_complete_download_is_verified_and_partial_or_changed_data_removed(signed,tmp_path):
    payload,body,public,encode=signed;update=updater.verify_manifest(encode(),'0.12.0',public)
    progress=[];path=updater.download_update(update,tmp_path/'good',lambda *a:progress.append(a),opener=lambda u:io.BytesIO(body))
    assert path.read_bytes()==body and progress[-1]==(len(body),len(body))
    for content in (body[:-1],body+b'x',body[:-1]+b'x'):
        cache=tmp_path/'bad'
        with pytest.raises(updater.UpdateError):updater.download_update(update,cache,opener=lambda u:io.BytesIO(content))
        assert list(cache.iterdir())==[]
    cancel=threading.Event();cancel.set()
    with pytest.raises(updater.UpdateError):updater.download_update(update,tmp_path/'cancel',cancel=cancel,opener=lambda u:io.BytesIO(body))
    assert list((tmp_path/'cancel').iterdir())==[]

def test_install_rechecks_bytes_and_runs_without_shell_or_quiet_flags(signed,tmp_path):
    payload,body,public,encode=signed;update=updater.verify_manifest(encode(),'0.12.0',public)
    file=tmp_path/'Desk update.exe';file.write_bytes(body);runs=[]
    updater.launch_installer(file,update,tmp_path,lambda *args,**kw:runs.append((args,kw)))
    args,kw=runs[0]
    assert args[0][0]==str(file) and '/NORESTART' in args[0] and '/NOCLOSEAPPLICATIONS' in args[0]
    assert not any('silent' in arg.lower() for arg in args[0]) and 'shell' not in kw
    file.write_bytes(body[:-1]+b'x')
    with pytest.raises(updater.UpdateError):updater.launch_installer(file,update,tmp_path,lambda *a,**k:runs.append(1))
    assert len(runs)==1

@pytest.mark.parametrize('url',['http://github.com/file','https://github.com.evil.test/file','https://user:pass@github.com/file','https://127.0.0.1/file','https://github.com:444/file'])
def test_redirect_transport_refuses_unexpected_origin(url):
    assert not updater._allowed_transport(url)

def test_update_ui_never_installs_during_session_and_requires_separate_local_click(tmp_path,monkeypatch):
    from novoacesso.app import MainWindow
    from PySide6.QtWidgets import QApplication
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    controller=window.updates;controller.installation=tmp_path;controller.available=updater.Update('0.12.1','url','0'*64,1024,'Teste de atualização')
    launched=[];quit_calls=[]
    monkeypatch.setattr(updater,'launch_installer',lambda *a:launched.append(a))
    monkeypatch.setattr(window,'quit_application',lambda:quit_calls.append(True))
    try:
        controller.show_offer();assert controller.dialog and not launched
        controller.on_downloaded(tmp_path/'test.exe','');assert not launched
        window.peer=SimpleNamespace(closed=threading.Event())
        controller.install();assert not launched and 'Encerre' in controller.message.text()
        window.peer=None;controller.install();assert len(launched)==1 and quit_calls==[True]
    finally:
        if controller.dialog:controller.dialog.close()
        window.close();QApplication.processEvents()

def test_windows_block_keeps_current_desk_open(tmp_path,monkeypatch):
    from novoacesso.app import MainWindow
    from PySide6.QtWidgets import QApplication
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();c=window.updates
    c.installation=tmp_path;c.available=updater.Update('0.12.1','url','0'*64,1024,'Teste')
    quits=[];monkeypatch.setattr(window,'quit_application',lambda:quits.append(True))
    def block(*args):
        ex=OSError('Policy block');ex.winerror=4551;raise ex
    monkeypatch.setattr(updater,'launch_installer',block)
    try:
        c.show_offer();c.on_downloaded(tmp_path/'test.exe','');c.install()
        assert not quits and 'Windows bloqueou' in c.message.text()
    finally:
        if c.dialog:c.dialog.close()
        window.close();QApplication.processEvents()

def test_missing_published_manifest_is_not_reported_as_already_current():
    from urllib.error import HTTPError
    def missing(url):raise HTTPError(url,404,'missing',{},None)
    with pytest.raises(updater.UpdateError,match='ainda não está disponível'):updater.check_update('0.12.3',opener=missing)

def test_each_manifest_check_refreshes_redirect_and_still_requires_signature(signed,monkeypatch):
    _,_,public,encode=signed;urls=[];original=updater.verify_manifest
    monkeypatch.setattr(updater,'verify_manifest',lambda data,version:original(data,version,public))
    def response(url):urls.append(url);return io.BytesIO(encode())
    assert updater.check_update('0.12.0',response).version=='0.12.1'
    assert updater.check_update('0.12.0',response).version=='0.12.1'
    assert urls[0]!=urls[1] and all(url.startswith(updater.MANIFEST_URL+'?desk_check=') for url in urls)

def test_update_page_shows_installed_version_result_and_clickable_notification(tmp_path,monkeypatch):
    from novoacesso.app import MainWindow
    from novoacesso import __version__
    from PySide6.QtWidgets import QApplication,QLabel
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();controller=window.updates
    try:
        window.open_update_settings();assert window.settings_navigation.currentItem().text()=='Atualizações'
        controller.on_checked(None,'',False)
        assert __version__ in window.update_status_label.text() and 'Última verificação:' in window.update_last_check.text()
        update=updater.Update('0.12.5','url','0'*64,1024,'Teste')
        controller.on_checked(update,'',False)
        assert window.update_offer_button.isVisibleTo(window.settings_page) and '0.12.5' in window.update_status_label.text()
        assert window.notifications.destination=='updates' and window.notifications.toast.isVisible()
        window.notifications.open_destination();assert controller.dialog and any('Desk 0.12.5 disponível' in label.text() for label in controller.dialog.findChildren(QLabel))
        controller.dialog.close();QApplication.processEvents()
        controller.on_checked(None,'Sem resposta do serviço de atualização.',False)
        assert 'Sem resposta' in window.update_status_label.text()
    finally:
        if controller.dialog:controller.dialog.close()
        window.close();QApplication.processEvents()
