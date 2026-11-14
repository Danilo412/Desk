from types import SimpleNamespace
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QCheckBox,QPushButton
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow,Prompt

def test_copy_address_never_substitutes_full_invitation(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    window=MainWindow()
    try:
        window.numeric_code.setText('1234 5678 9012');window.invite.setPlainText('NA1-synthetic-full-invitation')
        window.copy_invite()
        assert QApplication.clipboard().text()=='1234 5678 9012'
        assert window.windowTitle()=='Desk'
    finally:window.close();QTest.qWait(20)

def test_paste_and_enter_use_single_remote_address(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));calls=[]
    monkeypatch.setattr(MainWindow,'connect_peer',lambda self,*a:calls.append(self.remote_invite.toPlainText()))
    window=MainWindow()
    try:
        QApplication.clipboard().setText('  1234 5678 9012\n');window.paste_address()
        QTest.keyClick(window.remote_invite,Qt.Key.Key_Return)
        assert calls==['1234 5678 9012']
        assert window.remote_invite.text()=='1234 5678 9012'
    finally:window.close();QTest.qWait(20)

def test_empty_connect_keeps_incoming_listener(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();calls=[]
    monkeypatch.setattr(window,'stop_sharing',lambda:calls.append('stopped'))
    try:
        window.connect_peer()
        assert calls==[] and not window.connecting
    finally:window.close();QTest.qWait(20)

def test_stale_numeric_expiry_cannot_remove_current_address(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        window.numeric_invite=SimpleNamespace(id='current',stop=lambda:None)
        window.numeric_code.setText('1234 5678 9012')
        window.on_event('numeric_expired',{'id':'previous'})
        assert window.numeric_code.text()=='1234 5678 9012'
    finally:window.close();QTest.qWait(20)

def test_cancelled_consent_never_grants_access(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        prompt=Prompt('consent',{'address':'synthetic peer'});prompt.cancelled=True
        assert window.consent_dialog(prompt) is False
        assert window.permissions()==dict(control=False,clipboard=False,audio=False)
    finally:window.close();QTest.qWait(20)

def test_accept_applies_only_selected_session_permissions(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    class Host:
        peer=None;permissions={}
        def stop(self):pass
    window.host=Host()
    def accept():
        dialog=QApplication.activeModalWidget()
        for checkbox in dialog.findChildren(QCheckBox):checkbox.setChecked(checkbox.text()=='Mouse e teclado')
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Aceitar').click()
    try:
        QTimer.singleShot(0,accept)
        assert window.consent_dialog(Prompt('consent',{'address':'synthetic peer'}))
        assert window.host.permissions==dict(control=True,clipboard=False,audio=False)
    finally:window.close();QTest.qWait(20)

def test_stop_receiving_cancels_automatic_renewal(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        window.address_timer.start(10000);window.stop_all_sharing()
        assert not window._desk_listening_requested and not window.address_timer.isActive()
    finally:window.close();QTest.qWait(20)

def test_recent_history_does_not_store_invitation_secrets(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    monkeypatch.setattr(window,'_core_event',lambda *a:None)
    try:
        window.peer=SimpleNamespace(role='viewer');window._desk_last_remote='NAU1-synthetic-private-profile'
        window.on_event('connected',{})
        history=window.identity.settings()['desk_recents']
        assert history[0]['label']=='Computador autorizado'
        assert 'NAU1-' not in str(history)
    finally:window.peer=None;window.close();QTest.qWait(20)

def test_address_copy_paste_enter_consent_and_automatic_renewal(tmp_path,monkeypatch):
    import time
    from novoacesso import desktop,identity,numeric_invite
    from test_session import FakeDesktop
    from test_numeric_invite import Hub
    original=identity.IdentityStore;roots=iter([tmp_path/'host',tmp_path/'viewer'])
    monkeypatch.setattr(identity,'IdentityStore',lambda:original(next(roots)))
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    hub=Hub();monkeypatch.setattr(numeric_invite,'client_for',lambda *a,**k:hub.client())
    approvals=[];monkeypatch.setattr(MainWindow,'consent_dialog',lambda self,prompt:approvals.append(True) or True)
    host=MainWindow();viewer=MainWindow()
    def wait(predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return
            QTest.qWait(20)
        assert predicate()
    try:
        for window in (host,viewer):window.cloud_signaling_key='synthetic-directory';window.address.setCurrentText('127.0.0.1')
        host.prepare_address();wait(lambda:host._desk_address_online)
        first=host.numeric_code.text();host.copy_invite();viewer.paste_address()
        QTest.keyClick(viewer.remote_invite,Qt.Key.Key_Return)
        wait(lambda:viewer.canvas.image is not None)
        assert approvals==[True] and not viewer.canvas.allow_control
        assert host.numeric_code.text()==first
        assert viewer.identity.address_peer(host.identity.desk_address)==host.identity.public
        viewer.disconnect();wait(lambda:host._desk_address_online)
        assert host.numeric_code.text()==first
        viewer.canvas.image=None
        QTest.keyClick(viewer.remote_invite,Qt.Key.Key_Return)
        wait(lambda:viewer.peer and viewer.canvas.image is not None)
        assert approvals==[True,True] and host.numeric_code.text()==first
    finally:
        host.close();viewer.close();QTest.qWait(50)
