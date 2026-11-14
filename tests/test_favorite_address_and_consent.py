import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QComboBox,QPushButton
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow,Prompt
from novoacesso.identity import IdentityStore
from novoacesso.saved_connections import save_address,open_connection,list_connections,update_connection

def test_renaming_and_coloring_keep_protected_profile_encrypted(tmp_path):
    import pytest
    from novoacesso.saved_connections import save_connection
    from novoacesso.relay import token_encode
    identity=IdentityStore(tmp_path/'viewer')
    profile=token_encode('NAU1-',dict(v=1,host='127.0.0.1',port=4433,fp='ab'*32))
    id=save_connection(identity,'PC protegido',profile,'senha-local-teste')
    encrypted=identity.data['connections'][id]['sealed']
    update_connection(identity,id,name='Escritório',color='#64517a')
    restored=IdentityStore(identity.root)
    assert restored.data['connections'][id]['sealed']==encrypted
    assert profile not in str(restored.data['connections'])
    with pytest.raises(ValueError,match='Senha'):open_connection(restored,id,'senha-incorreta')
    assert open_connection(restored,id,'senha-local-teste')==profile

def test_address_favorite_survives_reload_and_never_adds_trust(tmp_path):
    identity=IdentityStore(tmp_path/'viewer');before=identity.data.get('trusted',{}).copy()
    id=save_address(identity,'PC de casa','1234 5678 9012');assert save_address(identity,'Casa','123456789012')==id
    update_connection(identity,id,name='Casa principal',color='#386357')
    restored=IdentityStore(identity.root);entry=list_connections(restored)[0]
    assert len(list_connections(restored))==1 and entry['name']=='Casa principal' and entry['color']=='#386357'
    assert open_connection(restored,id)=='123456789012' and restored.data.get('trusted',{})==before
    assert not restored.settings().get('unattended')

def test_enter_rejects_incoming_request_instead_of_accepting(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    def enter():
        dialog=QApplication.activeModalWidget()
        assert next(b for b in dialog.findChildren(QPushButton) if b.text()=='Recusar').isDefault()
        QTest.keyClick(dialog,Qt.Key.Key_Return)
    try:
        QTimer.singleShot(20,enter)
        assert window.consent_dialog(Prompt('consent',{'address':'127.0.0.1'})) is False
        assert not any(window.permissions().values())
    finally:window.close();QTest.qWait(20)

def test_read_only_profile_can_be_cancelled_without_changing_permissions(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    window.allow_control.setChecked(True);before=window.identity.settings().copy()
    def cancel():
        dialog=QApplication.activeModalWidget();profile=dialog.findChild(QComboBox)
        profile.setCurrentIndex(1)
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Recusar').click()
    try:
        QTimer.singleShot(20,cancel)
        assert window.consent_dialog(Prompt('consent',{'address':'127.0.0.1'})) is False
        assert window.allow_control.isChecked() and window.identity.settings()==before
    finally:window.close();QTest.qWait(20)

def test_numeric_favorite_reconnect_still_requests_each_consent(tmp_path,monkeypatch):
    from novoacesso import desktop,identity,numeric_invite
    from test_session import FakeDesktop
    from test_numeric_invite import Hub
    original=identity.IdentityStore;roots=iter([tmp_path/'host',tmp_path/'viewer'])
    monkeypatch.setattr(identity,'IdentityStore',lambda:original(next(roots)))
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    hub=Hub();monkeypatch.setattr(numeric_invite,'client_for',lambda *a,**k:hub.client())
    approvals=[];monkeypatch.setattr(MainWindow,'consent_dialog',lambda self,prompt:approvals.append(True) or True)
    host=MainWindow();viewer=MainWindow()
    def wait(predicate):
        end=time.monotonic()+8
        while time.monotonic()<end:
            if predicate():return
            QTest.qWait(20)
        assert predicate()
    try:
        for w in (host,viewer):w.cloud_signaling_key='synthetic-directory';w.address.setCurrentText('127.0.0.1')
        host.prepare_address();wait(lambda:host._desk_address_online)
        save_address(viewer.identity,'PC salvo',host.numeric_code.text());viewer.refresh_saved()
        for count in (1,2):
            viewer.canvas.image=None;viewer.saved_list.setCurrentRow(0);viewer.connect_saved()
            wait(lambda:viewer.canvas.image is not None)
            assert len(approvals)==count and not viewer.canvas.allow_control
            viewer.disconnect();wait(lambda:host._desk_address_online)
        assert viewer.identity.address_peer(host.identity.desk_address)==host.identity.public
    finally:host.close();viewer.close();QTest.qWait(50)
