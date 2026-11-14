import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import sys
import pytest
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow,STYLE
from test_session import FakeDesktop
_APP=None  # QApplication deve permanecer viva até o fim do processo de testes.

def test_migrates_old_trial_relay_and_preserves_trusted_devices(tmp_path,monkeypatch):
    import json
    from novoacesso import app as app_module
    from novoacesso.identity import IdentityStore
    from novoacesso.relay import token_encode
    state=tmp_path/'identity';identity=IdentityStore(state);controller=IdentityStore(tmp_path/'controller')
    key='pk_live_'+'a'*32
    identity.trust(controller.public,'previously approved')
    identity.configure(relay_config=token_encode('NAR1-',dict(mode='metered',api_key=key,ice_servers=[dict(urls='turn:global.relay.metered.ca:80',username='old-user',credential='old-test')])),use_relay=True)
    (tmp_path/'internet.json').write_text(json.dumps(dict(provider='ExpressTURN',public_key=key,ice_servers=[dict(urls=['turn:free.expressturn.com:3478?transport=tcp'],username='new-user',credential='new-client')])) )
    monkeypatch.setenv('NOVOACESSO_OFFLINE','0');monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(state))
    monkeypatch.setattr(app_module,'__file__',str(tmp_path/'src/novoacesso/app.py'))
    window=MainWindow()
    try:
        endpoint=window.relay_endpoint()
        assert endpoint['ice_servers'][0]['urls']==['turn:free.expressturn.com:3478?transport=tcp']
        persisted=IdentityStore(state)
        assert persisted.trusted(controller.public)
        assert persisted.settings()['relay_config']==window.relay_config.text()
    finally:window.close();QTest.qWait(30)

@pytest.mark.parametrize('_attempt',range(3))
def test_two_windows_consent_frame_and_disconnect(monkeypatch,_attempt):
    global _APP
    from novoacesso import desktop
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    approvals=[]
    def approve(*args,**kwargs):approvals.append(True);return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox,'question',approve)
    monkeypatch.setattr(MainWindow,'consent_dialog',lambda self,prompt:approve()==QMessageBox.StandardButton.Yes)
    _APP=QApplication.instance() or QApplication([]);_APP.setStyleSheet(STYLE)
    host=MainWindow();viewer=MainWindow();errors=[]
    monkeypatch.setattr(sys,'excepthook',lambda *args:errors.append(args))
    try:
        host.address.setCurrentText('127.0.0.1');host.start_host()
        assert host.invite.toPlainText().startswith('NA1-')
        viewer.remote_invite.setPlainText(host.invite.toPlainText());viewer.connect_peer()
        end=time.monotonic()+6
        while time.monotonic()<end and viewer.canvas.image is None:QTest.qWait(20)
        assert approvals and viewer.canvas.image is not None
        assert not viewer.canvas.allow_control
        host.allow_control.setChecked(True)
        end=time.monotonic()+3
        while time.monotonic()<end and not viewer.control.isEnabled():QTest.qWait(20)
        assert viewer.control.isEnabled()
        viewer.control.setChecked(True);assert viewer.canvas.allow_control
        host.allow_control.setChecked(False)
        end=time.monotonic()+3
        while time.monotonic()<end and viewer.canvas.allow_control:QTest.qWait(20)
        assert not viewer.canvas.allow_control
        viewer.disconnect();QTest.qWait(100)
        assert not viewer.peer and not errors
    finally:
        host.close();viewer.close();QTest.qWait(50)

def test_local_enrollment_then_trusted_reconnect_and_disable(monkeypatch,tmp_path):
    from novoacesso import desktop,identity
    original=identity.IdentityStore;roots=iter([tmp_path/'host',tmp_path/'viewer'])
    monkeypatch.setattr(identity,'IdentityStore',lambda:original(next(roots)))
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(MainWindow,'consent_dialog',lambda self,prompt:True)
    notes=[];monkeypatch.setattr(QMessageBox,'information',lambda *a:notes.append(a))
    host=MainWindow();viewer=MainWindow()
    def await_gui(predicate):
        end=time.monotonic()+5
        while time.monotonic()<end:
            if predicate():return
            QTest.qWait(20)
        assert predicate(),notes
    try:
        host.address.setCurrentText('127.0.0.1');host.start_host()
        viewer.remote_invite.setPlainText(host.invite.toPlainText());viewer.connect_peer()
        await_gui(lambda:host.peer and viewer.canvas.image is not None)
        host.trust_current();assert host.identity.trusted(viewer.identity.public)
        viewer.disconnect();await_gui(lambda:host.peer is None)
        host.unattended.setChecked(True)
        assert host.persistent and host.permanent_profile.toPlainText().startswith('NAU1-')
        viewer.remote_invite.setPlainText(host.permanent_profile.toPlainText());viewer.connect_peer()
        await_gui(lambda:host.peer and viewer.peer)
        assert host.peer.device_public==viewer.identity.public
        host.stop_all_sharing();await_gui(lambda:viewer.peer is None)
        assert not host.identity.settings()['unattended'] and not host.persistent and not notes
    finally:
        if host.unattended.isChecked():host.unattended.setChecked(False)
        host.close();viewer.close();QTest.qWait(50)
