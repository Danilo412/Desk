import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow
from novoacesso.identity import IdentityStore
from novoacesso.unattended import TrustedHost
from novoacesso.session import HostService,join
from novoacesso.saved_connections import save_connection,open_connection,list_connections,remove_connection
from test_session import FakeDesktop,wait_for

def test_fullscreen_only_canvas_escape_and_restore():
    window=MainWindow();window.show();QTest.qWait(50)
    old_width=window.canvas.width();events=[];window.canvas.input_event.connect(events.append)
    try:
        window.fullscreen();QTest.qWait(80)
        assert window.canvas.window() is window.fullscreen_window
        assert window.fullscreen_window.isFullScreen()
        assert window.fullscreen_window.layout().count()==1
        assert window.canvas.width()>old_width
        QTest.keyClick(window.canvas,Qt.Key.Key_Escape);QTest.qWait(50)
        assert not window._fullscreen and window.viewer.parent() is window.session_split
        assert window.tabs.currentIndex()==1
        assert not any(e.get('vk')==27 for e in events)
        window.fullscreen();QTest.qWait(30);window.disconnect()
        assert not window._fullscreen and window.viewer.parent() is window.session_split
    finally:window.close();QTest.qWait(30)

def test_latest_frame_mailbox_keeps_only_newest_image():
    from PIL import Image
    window=MainWindow()
    try:
        first=Image.new('RGB',(64,64),'red');last=Image.new('RGB',(64,64),'blue')
        for _ in range(100):window.emit_event('frame',first)
        window.emit_event('frame',last);window.render_latest_frame()
        assert window.latest_frame is None and window.canvas.image.pixelColor(0,0).blue()==255
    finally:window.close();QTest.qWait(20)

def test_capture_waits_for_congested_queue_before_encoding():
    import queue,threading,time
    from types import SimpleNamespace
    from novoacesso.session import Peer
    pending=queue.Queue();pending.put(b'old');pending.put(b'older');sent=[];desktop=FakeDesktop()
    channel=SimpleNamespace(outgoing=pending,control=lambda *a:None,close=lambda:None)
    peer=Peer(channel,'host',lambda *a:None,lambda *a:None,{},backend=desktop,monitors=desktop.monitors())
    def send(kind,payload):sent.append(kind);peer.closed.set()
    channel.send=send
    thread=threading.Thread(target=peer._capture);thread.start()
    try:
        time.sleep(.1);assert desktop.counter==0
        pending.get();thread.join(3)
        assert not thread.is_alive() and sent==[b'V']
    finally:peer.closed.set();thread.join(3)

def test_saved_password_profile_delivery_and_real_trusted_reconnect(tmp_path):
    host_identity=IdentityStore(tmp_path/'host');viewer_identity=IdentityStore(tmp_path/'viewer')
    events=[];received=[];host=HostService(FakeDesktop(),lambda *a:None,lambda *a:True,{},identity=host_identity)
    token=host.start('127.0.0.1',bind_address='127.0.0.1');peer=None;permanent=None;reconnected=None
    try:
        peer=join(token,lambda k,d:events.append((k,d)),lambda *a:None,identity=viewer_identity);peer.start()
        wait_for(lambda:host.peer)
        host_identity.trust(viewer_identity.public,'approved controller');host_identity.configure(unattended=True)
        permanent=TrustedHost(FakeDesktop(),lambda *a:None,lambda *a:False,{},identity=host_identity)
        profile=permanent.start('127.0.0.1',bind_address='127.0.0.1')
        host.peer.send(dict(type='permanent_profile',profile=profile,name='PC X'))
        wait_for(lambda:any(k=='permanent_profile' for k,d in events))
        delivered=next(d['profile'] for k,d in events if k=='permanent_profile')
        entry=save_connection(viewer_identity,'PC X',delivered,'password-for-test')
        reopened=IdentityStore(tmp_path/'viewer')
        assert list_connections(reopened)[0]['locked']
        assert delivered not in str(reopened.data['connections'])
        with pytest.raises(ValueError,match='Senha'):open_connection(reopened,entry,'wrong-password')
        saved=open_connection(reopened,entry,'password-for-test')
        peer.close();peer.wait_for_workers();peer=None;host.stop()
        reconnected=join(saved,lambda k,d:received.append(k),lambda *a:pytest.fail('Trusted reconnection cannot prompt'),identity=reopened);reconnected.start()
        wait_for(lambda:'frame' in received)
        host_identity.revoke(viewer_identity.public);wait_for(lambda:permanent.peer.closed.is_set())
        remove_connection(reopened,entry);assert not list_connections(reopened)
        with pytest.raises(Exception):save_connection(reopened,'temporary',token)
    finally:
        for connection in (peer,reconnected):
            if connection:connection.close();connection.wait_for_workers()
        host.stop()
        if permanent:permanent.stop()
