import threading,time
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QCheckBox
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow,Prompt
from novoacesso.session import HostService,join
from novoacesso.wire import connect_invitation
from test_session import FakeDesktop,wait_for

def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        QTest.qWait(15)
    assert predicate()

def test_remote_cancel_closes_real_dialog_and_next_request_connects(tmp_path,monkeypatch):
    from novoacesso import desktop
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'host'));host=MainWindow()
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'viewer'));viewer=MainWindow();viewer._desk_listening_requested=False
    original=host.consent_dialog;calls=[];elapsed=[]
    def consent(prompt):
        calls.append(prompt);started=[]
        def choose():
            if len(calls)==1:started.append(time.monotonic());viewer.disconnect()
            else:
                dialog=QApplication.activeModalWidget()
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Aceitar').click()
        QTimer.singleShot(60,choose);result=original(prompt)
        if started:elapsed.append(time.monotonic()-started[0]);assert not result
        return result
    host.consent_dialog=consent
    try:
        host.address.setCurrentText('127.0.0.1');host.start_host();token=host.invite.toPlainText()
        viewer.remote_invite.setText(token);viewer.connect_peer();wait(lambda:elapsed)
        wait(lambda:not host.prompts and not host.incoming_notice.isHidden())
        assert elapsed[0]<1.5 and QApplication.activeModalWidget() is None
        assert viewer.peer is None and host.peer is None and host.backend.counter==0 and host.backend.inputs==[]
        assert not host.host.used and not host.host.gate.locked()
        viewer.connect_peer();wait(lambda:viewer._connection_state=='active')
        assert len(calls)==2 and viewer.canvas.image is not None and not viewer.canvas.allow_control
    finally:host.close();viewer.close();QTest.qWait(40)

def test_cancellation_wins_before_accept_and_preserves_permissions(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();cancelled=threading.Event()
    before=window.identity.settings().copy()
    def cancel_and_accept():
        dialog=QApplication.activeModalWidget()
        for checkbox in dialog.findChildren(QCheckBox):checkbox.setChecked(True)
        cancelled.set()
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Aceitar').click()
    try:
        QTimer.singleShot(20,cancel_and_accept)
        assert window.consent_dialog(Prompt('consent',{'address':'127.0.0.1','_cancelled':cancelled.is_set})) is False
        assert not any(window.permissions().values()) and window.identity.settings()==before
        prompt=Prompt('consent',{'address':'127.0.0.1','_cancelled':cancelled.is_set});window.on_prompt(prompt)
        assert prompt.done.is_set() and not window.prompts
    finally:window.close();QTest.qWait(30)

def test_connection_closed_just_before_start_leaves_no_gui_peer(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    class ClosedPeer:
        address_lookup=None;connection_profile='';closed=False
        def start(self):raise ConnectionError('Link closed')
        def close(self):self.closed=True
    peer=ClosedPeer();peer.ui_epoch=window.connection_epoch
    try:
        window.on_joined(peer);wait(lambda:window._connection_state=='failed')
        assert window.peer is None and peer.closed and not window.canvas.allow_control
    finally:window.close();QTest.qWait(30)

def test_waiting_channel_rejects_media_before_approval():
    backend=FakeDesktop();ready=threading.Event();withdrawn=[];events=[]
    def request(kind,data,timeout):
        ready.set();wait_for(data['_cancelled'],2);withdrawn.append(True);return True
    host=HostService(backend,lambda k,d:events.append(k),request,dict(control=False,clipboard=False,audio=False))
    token=host.start('127.0.0.1');client=None
    try:
        client,data=connect_invitation(token);client.control(dict(type='hello',min=1,max=2,secret=data['secret']))
        assert ready.wait(2)
        client.send(b'V',b'unapproved data');wait_for(lambda:withdrawn and 'incoming_cancelled' in events)
        assert backend.counter==0 and host.peer is None and not host.used
        assert 'incoming_cancelled' in events
    finally:
        if client:client.close()
        host.stop()

@pytest.mark.parametrize('version',[1,2])
def test_raw_welcome_precedes_media_and_cancel_releases_gate(version):
    backend=FakeDesktop();host=HostService(backend,lambda *a:None,lambda *a:True,dict(control=False,clipboard=False,audio=False))
    token=host.start('127.0.0.1');client=None
    try:
        client,data=connect_invitation(token);client.control(dict(type='hello',min=1,max=version,secret=data['secret']))
        kind,welcome=client.receive()
        assert kind==b'J' and welcome['type']=='welcome' and welcome['version']==version
        client.version=version;client.start_io();wait_for(lambda:host.peer)
        kind,payload=client.receive();assert kind in (b'V',b'W',b'J')
        client.close();wait_for(lambda:host.peer.closed.is_set() and not host.gate.locked())
    finally:
        if client:client.close()
        host.stop()
