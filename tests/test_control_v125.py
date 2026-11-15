import ctypes,queue,threading,time
from types import SimpleNamespace
import pytest
from novoacesso.input_transport import InputCipher,FastInput,CAPABILITY
from novoacesso.desktop import DesktopBackend
from novoacesso.session import Peer

def make_peer(role='host',backend=None,outer=None):
    messages=[]
    channel=SimpleNamespace(sock=SimpleNamespace(outer=outer),control=messages.append,close=lambda:None,version=2,io_thread=None)
    peer=Peer(channel,role,lambda *args:None,lambda *args:None,{'control':True},backend)
    return peer,messages

def test_input_cipher_rejects_corruption_replay_cross_session_and_bad_size():
    sender=InputCipher(b'k'*32,b'p'*4);receiver=InputCipher(b'k'*32,b'p'*4)
    value=dict(type='input',event='button',button='left',down=True,x=.5,y=.4)
    packet=sender.seal(value);bad=bytearray(packet);bad[-1]^=1
    assert receiver.open(bytes(bad)) is None
    assert InputCipher(b'z'*32,b'p'*4).open(packet) is None
    assert receiver.open(packet)==value and receiver.open(packet) is None
    assert receiver.open(b'x'*537) is None
    assert receiver.open(sender.seal(dict(type='chat',text='x'))) is None

def test_fast_input_preserves_order_without_waiting_for_video_and_checks_permission():
    inputs=[];received=threading.Event();closed=threading.Event()
    backend=SimpleNamespace(input=lambda value:(inputs.append(value),received.set()),release=lambda:None)
    host,host_messages=make_peer(backend=backend,outer=SimpleNamespace(input_handler=None))
    viewer,viewer_messages=make_peer('viewer',outer=SimpleNamespace(send_input_packet=lambda packet:(host.fast_input.enqueue(packet) or True)))
    host.remote_media=viewer.remote_media={CAPABILITY}
    sender=viewer.fast_input.sender=InputCipher(b'k'*32,b'p'*4)
    host.fast_input.handle(dict(type='input_route',key=(b'k'*32).hex(),prefix=(b'p'*4).hex()))
    viewer.fast_input.handle(dict(type='input_route_ready'))
    try:
        values=[dict(type='input',event='button',button='left',down=True,x=.3,y=.4),dict(type='input',event='move',x=.8,y=.4),dict(type='input',event='button',button='left',down=False,x=.8,y=.4)]
        start=time.monotonic()
        for value in values:assert viewer.fast_input.send(value)
        deadline=time.monotonic()+1
        while len(inputs)<3 and time.monotonic()<deadline:time.sleep(.005)
        assert inputs==values and time.monotonic()-start<.5
        assert not viewer_messages # No input queued behind TLS video.
        host.set_permissions({'control':False});received.clear()
        viewer.fast_input.send(dict(type='input',event='key',vk=65,down=True))
        assert not received.wait(.1) and len(inputs)==3
        host.set_permissions({'control':True});host.control_state='protected'
        viewer.fast_input.send(dict(type='input',event='key',vk=65,down=True))
        assert not received.wait(.1)
    finally:host.close();viewer.close();host.wait_for_workers()

def test_switch_holds_dispatcher_until_tls_barrier_is_acknowledged():
    route_sent=threading.Event();commands=[]
    outer=SimpleNamespace(open_input_channel=lambda:True,send_input_packet=lambda packet:commands.append(packet) or True)
    peer,messages=make_peer('viewer',outer=outer);peer.remote_media={CAPABILITY}
    def send(value):
        messages.append(value)
        if value['type']=='input_route':route_sent.set()
    peer.send=send
    try:
        peer.fast_input.negotiate();assert route_sent.wait(1)
        peer.send_input(dict(event='button',button='left',down=True,x=.5,y=.5))
        time.sleep(.03);assert len(messages)==1 and not commands
        peer.fast_input.handle(dict(type='input_route_ready'))
        deadline=time.monotonic()+1
        while not commands and time.monotonic()<deadline:time.sleep(.005)
        assert len(commands)==1 and len(messages)==1
    finally:peer.close();peer.wait_for_workers()

def test_legacy_transport_keeps_tls_and_failed_active_route_does_not_race_fallback():
    peer,messages=make_peer('viewer')
    value=dict(type='input',event='release');peer._dispatch_input(value);assert messages==[value]
    peer.fast_input.outer=SimpleNamespace(send_input_packet=lambda packet:False)
    peer.fast_input.sender=InputCipher(b'k'*32,b'p'*4);peer.fast_input.ready.set()
    peer._dispatch_input(value)
    assert peer.closed.is_set() and messages==[value]

def test_native_input_rejection_does_not_disconnect_or_remove_permission():
    fail=[True];inputs=[]
    def apply(value):
        if fail[0]:raise OSError(5,'denied')
        inputs.append(value)
    peer,messages=make_peer(backend=SimpleNamespace(input=apply,release=lambda:None))
    peer.apply_input(dict(event='move',x=.5,y=.5))
    assert peer.control_state=='denied' and not peer.closed.is_set() and peer.permissions['control']
    fail[0]=False;peer.apply_input(dict(event='move',x=.6,y=.5))
    assert len(inputs)==1 and peer.control_state=='desktop'

@pytest.mark.parametrize('desktop,read_ok,expected',[(None,True,'protected'),('Winlogon',True,'protected'),('Default',True,'desktop'),('Default',False,'protected')])
def test_desktop_probe_is_read_only_and_always_closes_handle(desktop,read_ok,expected):
    closed=[]
    class User:
        def OpenInputDesktop(self,flags,inherit,rights):
            assert (flags,inherit,rights)==(0,False,1)
            return 77 if desktop else 0
        def GetUserObjectInformationW(self,handle,info,buffer,size,needed):
            assert info==2;buffer.value=desktop;return read_ok
        def CloseDesktop(self,handle):closed.append(handle)
    backend=DesktopBackend.__new__(DesktopBackend);backend.user=User()
    assert backend.input_desktop_state()==expected
    assert closed==([77] if desktop else [])

def test_capture_separate_cursor_excludes_hardware_pointer(monkeypatch):
    from novoacesso.capture import CaptureSource
    options=[]
    class Screen:
        monitors=[dict(left=0,top=0,width=32,height=32)]*2
        def grab(self,rect):return SimpleNamespace(size=(32,32),bgra=b'\0\0\0\xff'*1024)
        def close(self):pass
    monkeypatch.setattr('novoacesso.capture.mss.MSS',lambda **kwargs:(options.append(kwargs) or Screen()))
    with CaptureSource() as source:
        source.separate_cursor=True;assert source.image(1).size==(32,32)
        assert source.backend=='MSS' and source.camera is None
    assert options==[{'with_cursor':False}]

def test_lock_warning_and_resume_preserve_the_viewers_control_choice():
    from novoacesso.app import MainWindow
    window=MainWindow();sent=[]
    peer=SimpleNamespace(role='viewer',permissions={'control':True},control_state='desktop',send_input=sent.append)
    try:
        window.peer=peer;window.control.setChecked(True);window.control_changed()
        assert window.canvas.allow_control
        peer.control_state='protected';window.on_event('control_state',dict(state='protected'))
        assert not window.canvas.allow_control and window.canvas.control_blocked and 'senha' in window.control_hint.text() and window.control.isChecked()
        peer.control_state='desktop';window.on_event('control_state',dict(state='desktop'))
        assert window.canvas.allow_control and not window.canvas.control_blocked
        peer.control_state='denied';window.on_event('control_state',dict(state='denied'))
        assert window.canvas.allow_control and 'janela' in window.activity.text() and 'senha' not in window.activity.text()
        window.control.setChecked(False)
        peer.control_state='protected';window.on_event('control_state',dict(state='protected'))
        peer.control_state='desktop';window.on_event('control_state',dict(state='desktop'))
        assert not window.canvas.allow_control and not window.control.isChecked()
    finally:window.peer=None;window.quit_application()

def test_capture_pauses_on_protected_desktop_and_resumes_without_disconnect():
    from contextlib import nullcontext
    from PIL import Image
    failed=threading.Event();frame=threading.Event();calls=[]
    class Backend:
        def capture_source(self):return nullcontext(SimpleNamespace(separate_cursor=False))
        def capture(self,*args):
            calls.append(1)
            if len(calls)==1:failed.set();raise OSError(5,'protected desktop')
            return Image.new('RGB',(64,64),'navy')
        def input_desktop_state(self):return 'protected'
        def release(self):pass
    peer,messages=make_peer(backend=Backend());peer.channel.version=1
    peer.channel.outgoing=SimpleNamespace(qsize=lambda:0)
    peer.channel.send=lambda *args:frame.set()
    try:
        thread=peer.spawn(peer._capture);assert failed.wait(1)
        deadline=time.monotonic()+1
        while peer.control_state!='protected' and time.monotonic()<deadline:time.sleep(.005)
        assert peer.control_state=='protected' and not peer.closed.is_set() and not frame.is_set()
        peer.report_control_state('desktop');assert frame.wait(1) and not peer.closed.is_set()
    finally:peer.close();peer.wait_for_workers()
