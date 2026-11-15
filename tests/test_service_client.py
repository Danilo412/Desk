import math,struct,threading,time
from types import SimpleNamespace
import pytest
from novoacesso.service_client import BrokerClient,FRAME,decode_frame,input_packet
from novoacesso.desktop import DesktopBackend

def test_input_protocol_includes_click_position_and_native_key_up():
    value=input_packet(dict(event='button',button='back',down=True,x=.4,y=.8))
    assert value[:4]==bytes((4,3,3,1)) and struct.unpack('<dd',value[4:])==(.4,.8)
    assert input_packet(dict(event='key',vk=13,down=False))==bytes((4,2,13,0,0))
    assert input_packet(dict(event='release'))==bytes((4,5))

@pytest.mark.parametrize('value',[
    dict(event='move',x=math.nan,y=.5),dict(event='move',x=math.inf,y=.5),dict(event='move',x=True,y=.5),
    dict(event='button',button='left',down=1,x=.5,y=.5),dict(event='key',vk=0,down=True),dict(event='key',vk=True,down=True),
    dict(event='wheel',delta=1201),dict(event='wheel',delta=True),dict(event='shell',command='anything')])
def test_service_rejects_unbounded_or_untyped_input(value):
    with pytest.raises(ValueError):input_packet(value)

def frame_reply():
    return b'\0'+FRAME.pack(-100,0,2,2,-100,0,102,2,2,2,8)+bytes((0,0,255,0,255,0,0,0))*2

def test_frame_is_bounded_and_preserves_monitor_geometry_and_color():
    image,rect,virtual=decode_frame(frame_reply(),1920,1080)
    assert image.size==(2,2) and image.getpixel((0,0))==(255,0,0) and image.getpixel((1,0))==(0,255,0)
    assert rect==dict(left=-100,top=0,width=2,height=2) and virtual['width']==102
    with pytest.raises(ValueError):decode_frame(frame_reply()[:-1],1920,1080)
    malformed=bytearray(frame_reply());struct.pack_into('<I',malformed,37,1234)
    with pytest.raises(ValueError):decode_frame(bytes(malformed),1920,1080)

def test_service_connection_exists_only_inside_an_authorized_host_lease():
    calls=[];pipes=[]
    class Pipe:
        def __init__(self,c):pipes.append(self);self.closed=False
        def exchange(self,p,timeout):calls.append(p);return b'\0\1' if p==b'\x01' else b'\0'
        def close(self):self.closed=True
    broker=BrokerClient(Pipe,{'fixture':True})
    assert not broker.available() and not pipes
    with pytest.raises(OSError):broker.input(dict(event='key',vk=65,down=True))
    broker.begin_session();assert broker.available() and len(pipes)==1
    broker.input(dict(event='move',x=.5,y=.5));broker.end_session()
    assert pipes[0].closed and not broker.available()
    broker.begin_session();assert broker.available() and len(pipes)==2
    broker.end_session()

def test_disconnect_cancels_in_flight_capture_and_rejects_late_reply():
    entered=threading.Event();resume=threading.Event();errors=[]
    class Pipe:
        def __init__(self,c):pass
        def exchange(self,p,timeout):entered.set();resume.wait(2);return frame_reply()
        def close(self):resume.set()
    broker=BrokerClient(Pipe,{'fixture':True});broker.begin_session()
    def capture():
        try:broker.capture(1,1920)
        except OSError:errors.append('cancelled')
    worker=threading.Thread(target=capture);worker.start();assert entered.wait(1)
    start=time.monotonic();broker.end_session();worker.join(1)
    assert time.monotonic()-start<.5 and not worker.is_alive() and errors==['cancelled']

def test_missing_service_does_not_claim_windows_lock_is_controllable():
    backend=DesktopBackend.__new__(DesktopBackend);backend.local_desktop_state=lambda:'protected'
    backend.secure=BrokerClient(configuration={});backend.secure.config=None;backend.secure.begin_session()
    assert backend.input_desktop_state()=='protected'
    backend.local_desktop_state=lambda:'desktop';assert backend.input_desktop_state()=='desktop'

def test_ready_service_can_supply_protected_frame_without_native_user_input():
    received=[]
    class Pipe:
        def __init__(self,c):pass
        def exchange(self,p,timeout):received.append(p);return b'\0\1' if p[0]==1 else frame_reply() if p[0]==3 else b'\0'
        def close(self):pass
    backend=DesktopBackend.__new__(DesktopBackend);backend.lock=threading.RLock();backend.rect=None;backend.virtual_rect=None
    backend.secure=BrokerClient(Pipe,{'fixture':True});backend.begin_secure_session();backend.local_desktop_state=lambda:'protected'
    assert backend.input_desktop_state()=='desktop'
    source=SimpleNamespace(backend='MSS',unchanged=True)
    assert backend.capture(source,1,1920).size==(2,2) and source.backend=='Serviço Windows' and not source.unchanged
    assert backend.rect['left']==-100 and backend.virtual_rect['width']==102
    backend.end_secure_session();assert backend.input_desktop_state()=='protected'

def test_peer_gates_privileged_lease_on_host_control_permission_and_revocation():
    from novoacesso.session import Peer
    events=[]
    backend=SimpleNamespace(begin_secure_session=lambda:events.append('begin'),end_secure_session=lambda:events.append('end'),release=lambda:events.append('release'))
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def start_io(self):pass
        def control(self,value):pass
        def close(self):self.closed.set()
    peer=Peer(Channel(),'host',lambda *args:None,lambda *args:None,{'control':False},backend)
    peer.spawn=lambda fn:None
    peer.start();assert not events
    peer.set_permissions({'control':True});assert events==['begin']
    peer.set_permissions({'control':False});assert events==['begin','release','end']
    peer.close();assert events[-2:]==['end','release']
