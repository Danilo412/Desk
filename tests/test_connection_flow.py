import threading,time
from types import SimpleNamespace
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QPushButton,QComboBox,QLineEdit
from PySide6.QtTest import QTest
from PIL import Image
from novoacesso.app import MainWindow

def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        QTest.qWait(20)
    assert predicate()

def test_cancel_discards_late_join_frames_and_stages(tmp_path,monkeypatch):
    from novoacesso.wire import make_invitation
    from novoacesso import session
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    entered=threading.Event();release=threading.Event();channel=SimpleNamespace(close=lambda:None)
    class Peer:
        closed=False;started=False
        def close(self):self.closed=True
        def start(self):self.started=True
    peer=Peer()
    def join(token,event,request,on_channel=None,identity=None):
        on_channel(channel);entered.set();release.wait(4)
        event('frame',Image.new('RGB',(64,64),'red'));return peer
    monkeypatch.setattr(session,'join',join);window=MainWindow()
    try:
        window.remote_invite.setPlainText(make_invitation('127.0.0.1',4433,'ab'*32)[1]);window.connect_peer()
        wait(entered.is_set);old_epoch=window.connection_epoch;window.disconnect();release.set();wait(lambda:peer.closed)
        window.on_event('connect_stage',{'epoch':old_epoch,'stage':'approval','text':'Old request'})
        window.on_event('connect_error',{'epoch':old_epoch,'text':'Old failure'})
        window.render_latest_frame()
        assert not peer.started and window.peer is None and window.canvas.image is None
        assert window._connection_state=='cancelled' and not window.canvas.allow_control
    finally:release.set();window.close();QTest.qWait(40)

def test_connect_approve_remote_screen_end_and_reject(tmp_path,monkeypatch):
    from novoacesso import desktop,identity,numeric_invite
    from novoacesso.saved_connections import save_address
    from test_session import FakeDesktop
    from test_numeric_invite import Hub
    original=identity.IdentityStore;roots=iter([tmp_path/'host',tmp_path/'viewer'])
    monkeypatch.setattr(identity,'IdentityStore',lambda:original(next(roots)));monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    hub=Hub();monkeypatch.setattr(numeric_invite,'client_for',lambda *a,**k:hub.client())
    states=[];show=MainWindow.show_connection_state
    monkeypatch.setattr(MainWindow,'show_connection_state',lambda self,state,detail='':(show(self,state,detail),states.append((self,state)))[0])
    original_consent=MainWindow.consent_dialog;decisions=iter(['Aceitar','Recusar'])
    def consent(self,prompt):
        decision=next(decisions)
        def choose():
            dialog=QApplication.activeModalWidget();dialog.findChild(QComboBox).setCurrentIndex(1)
            next(b for b in dialog.findChildren(QPushButton) if b.text()==decision).click()
        QTimer.singleShot(60,choose);return original_consent(self,prompt)
    monkeypatch.setattr(MainWindow,'consent_dialog',consent)
    host=MainWindow();viewer=MainWindow();host.show();viewer.show()
    try:
        for w in (host,viewer):w.cloud_signaling_key='synthetic-directory';w.address.setCurrentText('127.0.0.1')
        host.prepare_address();wait(lambda:host._desk_address_online)
        save_address(viewer.identity,'PC do teste',host.numeric_code.text());viewer.refresh_saved();viewer.saved_list.setCurrentRow(0);viewer.connect_saved()
        wait(lambda:viewer._connection_state=='active')
        assert viewer.tabs.currentIndex()==1 and viewer.connection_overlay.isHidden() and viewer.canvas.image is not None
        assert not viewer.canvas.allow_control and host._connection_state=='sharing'
        assert all((viewer,state) in states for state in ('locating','connecting','approval','receiving','active'))
        viewer.message.setText('synthetic chat');viewer.send_chat();wait(lambda:'synthetic chat' in host.chat.toPlainText())
        viewer.fullscreen();QTest.qWait(40);QTest.keyClick(viewer.canvas,Qt.Key.Key_Escape);QTest.qWait(40)
        assert not viewer._fullscreen and viewer.viewer.parent() is viewer.session_split
        viewer.disconnect();assert viewer.canvas.image is None and viewer.peer is None
        wait(lambda:host._desk_address_online)
        viewer.saved_list.setCurrentRow(0);viewer.connect_saved();wait(lambda:viewer._connection_state=='failed')
        assert viewer.peer is None and viewer.canvas.image is None and not viewer.canvas.allow_control
        assert viewer.connection_overlay.primary.text()=='Tentar novamente'
        assert QApplication.activeModalWidget() is None
    finally:host.close();viewer.close();QTest.qWait(60)

def test_invalid_favorite_address_stays_in_form_without_saving(tmp_path,monkeypatch):
    from novoacesso.saved_connections import list_connections
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();observed=[]
    def fill():
        dialog=QApplication.activeModalWidget();fields=dialog.findChildren(QLineEdit)
        fields[0].setText('123');fields[1].setText('PC')
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Salvar favorito').click()
        observed.append(dialog.isVisible() and not list_connections(window.identity));dialog.reject()
    try:
        QTimer.singleShot(20,fill);window.add_address_favorite();assert observed==[True]
    finally:window.close();QTest.qWait(30)
