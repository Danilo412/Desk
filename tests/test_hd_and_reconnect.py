import threading,time
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QMessageBox
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow
from novoacesso.codec import ScreenEncoder,ScreenDecoder
from novoacesso.desktop import DesktopBackend
from novoacesso.identity import IdentityStore
from novoacesso.unattended import TrustedHost
from novoacesso.saved_connections import save_connection,open_connection,list_connections,update_preferences
from novoacesso.wire import MAX_RECORD
from test_session import FakeDesktop

@pytest.mark.parametrize('size',[(1920,1080),(2560,1440)])
def test_hd_exact_text_and_changed_blocks(size):
    image=Image.new('RGB',size,'#e2e6ed');draw=ImageDraw.Draw(image)
    for y in range(20,size[1],60):draw.text((30,y),'HD desktop: sharp text 0123456789',fill='black',font_size=24)
    encoder=ScreenEncoder();decoder=ScreenDecoder()
    packet,stats=encoder.encode(image,'deflate',now=10)
    assert (stats['width'],stats['height'])==size and len(packet)<MAX_RECORD
    assert decoder.decode(packet).tobytes()==image.tobytes()
    packet,stats=encoder.encode(image,'deflate',now=20)
    assert stats['tiles']==0  # Static screen does not consume a full refresh every 5s.
    image.putpixel((200,200),(255,20,0));packet,stats=encoder.encode(image,'deflate',now=20.1)
    assert stats['tiles']==1 and decoder.decode(packet).tobytes()==image.tobytes()

def test_capture_hd_dimensions_and_bgra_channels():
    image=Image.new('RGB',(2560,1440),(24,90,180));shot=SimpleNamespace(size=image.size,bgra=image.tobytes('raw','BGRX'))
    source=SimpleNamespace(monitors=[dict(left=0,top=0,width=2560,height=1440)]*2,grab=lambda rect:shot)
    backend=DesktopBackend.__new__(DesktopBackend);backend.lock=threading.RLock();backend.rect=None
    assert backend.capture(source,1,1920).size==(1920,1080)
    native=backend.capture(source,1,2560)
    assert native.size==(2560,1440) and native.getpixel((0,0))==(24,90,180)

def await_gui(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        QTest.qWait(20)
    assert predicate()

def test_saved_hd_settings_and_automatic_reconnect_then_manual_stop(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'viewer'))
    monkeypatch.setattr(QMessageBox,'information',lambda *a:None)
    identity=IdentityStore(tmp_path/'host');window=MainWindow();host=None
    try:
        assert window.quality.currentData()==(1920,30)
        identity.configure(unattended=True);identity.trust(window.identity.public,'approved')
        host=TrustedHost(FakeDesktop(),lambda *a:None,lambda *a:False,{},identity=identity)
        profile=host.start('127.0.0.1',bind_address='127.0.0.1')
        view=dict(width=2560,fps=60,codec='deflate',auto_reconnect=True,display='fit')
        id=save_connection(window.identity,'PC HD',profile,'local-test-password',view=view)
        assert open_connection(window.identity,id,'local-test-password')==profile
        assert list_connections(IdentityStore(tmp_path/'viewer'))[0]['view']==view
        # Update preferences without asking for the stored profile's password again.
        update_preferences(window.identity,id,dict(width=1920,fps=30,codec='auto',auto_reconnect=True))
        monkeypatch.setattr('novoacesso.app.QInputDialog.getText',lambda *a:('local-test-password',True))
        window.refresh_saved();window.saved_list.setCurrentRow(0);window.connect_saved()
        await_gui(lambda:window.peer is not None and window.canvas.image is not None)
        assert window.quality.currentData()==(1920,30)
        window.quality.setCurrentIndex(next(i for i in range(window.quality.count()) if tuple(window.quality.itemData(i))==(2560,60)))
        assert list_connections(window.identity)[0]['view']['width']==2560
        old=window.peer;host.peer.close('simulated transient network interruption')
        await_gui(lambda:window.peer is not None and window.peer is not old,seconds=10)
        assert not window.manual_disconnect
        window.disconnect();QTest.qWait(1300)
        assert window.peer is None and not window.retry_timer.isActive() and window.manual_disconnect
        window.reconnect_profile=profile;window.manual_disconnect=False
        window.on_event('connect_error',dict(text='authorization revoked',retryable=False))
        assert window.manual_disconnect and not window.retry_timer.isActive()
    finally:
        window.close();QTest.qWait(30)
        if host:host.stop()
