import json,struct,time
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QTimer,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from novoacesso.app import MainWindow,RemoteCanvas,Prompt
from novoacesso.identity import IdentityStore
from novoacesso.saved_connections import save_address,remember_authorized,open_connection,list_connections,save_connection,authorized_for_address
from novoacesso.relay import token_encode
from novoacesso.multiplex import Outgoing,Incoming
from novoacesso.wire import MAX_RECORD,MAX_CONTROL,ProtocolError

def test_mouse_coalesces_without_reordering_clicks_or_keys():
    out=Outgoing();incoming=Incoming(MAX_RECORD,MAX_CONTROL,ProtocolError)
    def put(event,**data):
        payload=json.dumps(dict(type='input',event=event,**data)).encode();out.put(b'J'+struct.pack('>I',len(payload))+payload)
    for x in range(100):put('move',x=x/100,y=.5)
    put('button',down=True,button='left',x=.99,y=.5)
    for x in range(100):put('move',x=x/100,y=.6)
    put('button',down=False,button='left',x=.99,y=.6);put('key',vk=65,down=True)
    values=[]
    while out.qsize():
        result=incoming.feed(out.get_nowait()[5:])
        if result:values.append(json.loads(result[1]))
    assert [v['event'] for v in values]==['move','button','move','button','key']
    assert values[0]['x']==.99 and values[2]['x']==.99

def test_double_click_tab_repeat_cursor_and_drag_release():
    canvas=RemoteCanvas();canvas.resize(640,360);canvas.set_frame(Image.new('RGB',(640,360)));canvas.allow_control=True;canvas.show();QTest.qWait(30)
    events=[];canvas.input_event.connect(events.append)
    try:
        QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,100))
        QTest.mouseDClick(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,100))
        QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,100))
        assert [e['down'] for e in events if e['event']=='button']==[True,False,True,False]
        canvas.setFocus();assert canvas.focusNextPrevChild(True) is False
        repeat=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_A,Qt.KeyboardModifier.NoModifier,0,65,0,'a',True,1)
        QApplication.sendEvent(canvas,repeat);assert any(e.get('vk')==65 and e.get('down') for e in events)
        canvas.update_remote_cursor('ibeam');assert canvas.cursor().shape()==Qt.CursorShape.IBeamCursor
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,100));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(-5,100))
        assert not canvas.pressed_buttons and events[-1]['event']=='button' and events[-1]['down'] is False and events[-1]['x']==0
    finally:canvas.close()

def test_authorized_profile_promotes_favorite_and_preserves_password(tmp_path):
    store=IdentityStore(tmp_path/'viewer');address='123456789012';profile=token_encode('NAU1-',dict(v=1,host='127.0.0.1',port=45737,fp='ab'*32))
    id=save_address(store,'Meu PC',address)
    assert remember_authorized(store,'Nome remoto',profile,address)==id
    assert len(list_connections(store))==1 and list_connections(store)[0]['name']=='Meu PC'
    assert authorized_for_address(store,address)['id']==id and open_connection(store,id)==profile
    assert save_connection(store,'Meu PC',profile,'senha-local-teste')==id
    assert len(list_connections(store))==1 and authorized_for_address(store,address)['locked']
    assert 'profile' not in store.data['connections'][id]
    locked=IdentityStore(tmp_path/'locked');locked_id=save_connection(locked,'PC protegido',profile,'senha-local-teste')
    sealed=locked.data['connections'][locked_id]['sealed']
    assert remember_authorized(locked,'Outro nome',profile,address)==locked_id
    assert locked.data['connections'][locked_id]['sealed']==sealed and 'profile' not in locked.data['connections'][locked_id]

def test_consent_exposes_revocable_reconnect_and_reject_never_trusts(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();public=IdentityStore(tmp_path/'remote').public
    try:
        prompt=Prompt('consent',dict(address='127.0.0.1',device_public=public))
        dialog,_=window.build_consent_window(prompt)
        assert dialog.remember_device.isEnabled() and dialog.remember_device.isChecked()
        dialog.deleteLater()
        QTimer.singleShot(20,lambda:QApplication.activeModalWidget().reject())
        assert window.consent_dialog(prompt) is False
        assert window._remember_approved_public is None and not window.identity.trusted(public)
    finally:window.close();QTest.qWait(20)

def test_fullscreen_preserves_aspect_and_restores_display_mode():
    window=MainWindow();window.show();window.show_connection_state('active');window.canvas.set_frame(Image.new('RGB',(1920,1080)));window.display.setCurrentIndex(window.display.findData('stretch'));QTest.qWait(40)
    try:
        window.fullscreen();QTest.qWait(50)
        assert window.fullscreen_window.windowFlags()&Qt.WindowType.FramelessWindowHint
        assert window.fullscreen_window.isFullScreen() and window.canvas.display_mode=='fit'
        assert abs(window.canvas.rect.width()/window.canvas.rect.height()-16/9)<.01
        assert window.fullscreen_window.geometry()==window.screen().geometry()
        window.exit_fullscreen();assert window.canvas.display_mode=='stretch' and window.viewer.parent() is window.session_split
    finally:window.close();QTest.qWait(20)

def test_first_accept_saves_and_trusted_reconnect_does_not_prompt(tmp_path,monkeypatch):
    from novoacesso import desktop,identity,numeric_invite
    from test_session import FakeDesktop
    from test_numeric_invite import Hub
    original=identity.IdentityStore;roots=iter([tmp_path/'host',tmp_path/'viewer'])
    monkeypatch.setattr(identity,'IdentityStore',lambda:original(next(roots)))
    monkeypatch.setattr(desktop,'DesktopBackend',FakeDesktop)
    hub=Hub();monkeypatch.setattr(numeric_invite,'client_for',lambda *a,**k:hub.client())
    host=MainWindow();viewer=MainWindow();approvals=[]
    def approve(prompt):
        approvals.append(True);host._remember_approved_public=prompt.data['device_public'];return True
    monkeypatch.setattr(host,'consent_dialog',approve)
    def wait(predicate):
        end=time.monotonic()+10
        while time.monotonic()<end:
            if predicate():return
            QTest.qWait(15)
        assert predicate()
    try:
        for w in (host,viewer):w.cloud_signaling_key='synthetic-directory';w.address.setCurrentText('127.0.0.1')
        host.prepare_address();wait(lambda:host._desk_address_online)
        number=host.identity.desk_address;viewer.remote_invite.setPlainText(number);viewer.connect_peer()
        wait(lambda:viewer.canvas.image is not None and viewer.available_profile)
        assert len(approvals)==1 and host.identity.trusted(viewer.identity.public)
        saved=authorized_for_address(viewer.identity,number);assert saved and len(list_connections(viewer.identity))==1
        viewer.disconnect();wait(lambda:not host.peer)
        viewer.remote_invite.setPlainText(number);viewer.connect_peer();wait(lambda:viewer.canvas.image is not None and viewer.peer)
        assert len(approvals)==1 and viewer.peer.connection_profile.startswith('NAU1-')
        host.identity.revoke(viewer.identity.public);wait(lambda:viewer.peer is None)
    finally:
        for w in (viewer,host):w.force_exit=True;w.close()
        QTest.qWait(50)

def test_second_instance_restores_first_without_duplicate_service(tmp_path):
    import concurrent.futures
    from novoacesso.single_instance import SingleInstance
    first=SingleInstance(tmp_path/'one');second=SingleInstance(tmp_path/'one');other=SingleInstance(tmp_path/'other');reopened=[]
    def notify(background=False):
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future=pool.submit(second.acquire,background)
            deadline=time.monotonic()+3
            while not future.done() and time.monotonic()<deadline:QTest.qWait(10)
            return future.result(1)
    try:
        assert first.acquire();first.callback=lambda:reopened.append(True);QTest.qWait(30)
        assert not notify();QTest.qWait(30);assert reopened==[True]
        assert not notify(background=True);QTest.qWait(30);assert reopened==[True]
        assert other.acquire()
        first.close();assert second.acquire()
    finally:first.close();second.close();other.close()
