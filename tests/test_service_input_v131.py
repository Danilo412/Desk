"""Pure regression checks: no Windows desktop input or service activation."""
import json,threading
from types import SimpleNamespace
import pytest
from PIL import Image
from novoacesso.desktop import DesktopBackend,DesktopInputError
from novoacesso.service_client import BrokerClient,input_packet

RECT=dict(left=0,top=0,width=1920,height=1080)

class Service:
    def __init__(self):
        self.authorized=False;self.generation=1;self.captured=False;self.calls=[]
        self.rect=RECT.copy();self.virtual=RECT.copy();self.change_during_capture=False
    def begin_session(self):self.authorized=True
    def end_session(self):self.authorized=False
    def available(self):return self.authorized
    def input_state(self):return self.generation,self.captured
    def capture(self,index,width):
        self.calls.append(('capture',index,width));self.captured=True
        if self.change_during_capture:self.generation+=1;self.change_during_capture=False
        return Image.new('RGB',(64,64)),self.rect.copy(),self.virtual.copy()
    def input(self,value):
        assert self.authorized and self.captured
        input_packet(value);self.calls.append(('input',value.copy()))
    def release(self):self.calls.append(('release',))

def backend():
    value=DesktopBackend.__new__(DesktopBackend)
    value.lock=threading.RLock();value.rect=RECT.copy();value.virtual_rect=RECT.copy()
    value.capture_monitor=1;value.capture_width=1920;value.keys=set();value.buttons=set()
    value.secure=Service();value.local_desktop_state=lambda:'desktop'
    def refused_native(*args):raise AssertionError('Must use the administrator-bound broker')
    value.user=SimpleNamespace(SendInput=refused_native)
    value.begin_secure_session();return value

def test_authorized_service_controls_default_desktop_and_primes_capture_only_once():
    value=backend()
    for i in range(30):value.input(dict(event='move',x=i/30,y=.5))
    value.input(dict(event='button',button='left',down=True,x=.5,y=.5))
    value.input(dict(event='button',button='left',down=False,x=.5,y=.5))
    value.input(dict(event='key',vk=65,down=True));value.input(dict(event='key',vk=65,down=False))
    assert len([c for c in value.secure.calls if c[0]=='capture'])==1
    assert len([c for c in value.secure.calls if c[0]=='input'])==34
    value.end_secure_session();assert not value.service_input_route and not value.secure.authorized

def test_desktop_change_invalidates_cached_capture_even_with_identical_monitor_size():
    value=backend();value.input(dict(event='move',x=.2,y=.3))
    value.secure.generation+=1;value.secure.captured=False
    value.input(dict(event='key',vk=65,down=True))
    assert len([c for c in value.secure.calls if c[0]=='capture'])==2

def test_switch_during_capture_rejects_input_until_capture_is_stable():
    value=backend();value.secure.change_during_capture=True
    with pytest.raises(DesktopInputError) as error:value.input(dict(event='key',vk=65,down=True))
    assert error.value.input_reason=='desktop_changed'
    assert not [c for c in value.secure.calls if c[0]=='input']
    value.input(dict(event='key',vk=65,down=True))
    assert len([c for c in value.secure.calls if c[0]=='input'])==1

def test_different_service_monitor_geometry_cannot_inject_into_wrong_screen():
    value=backend();value.secure.rect['left']=1920
    with pytest.raises(DesktopInputError) as error:value.input(dict(event='button',button='left',down=True,x=.5,y=.5))
    assert error.value.input_reason=='geometry_mismatch'
    assert not [c for c in value.secure.calls if c[0]=='input']

def test_service_input_before_first_frame_is_rejected_without_native_fallback():
    value=backend();value.rect=None
    with pytest.raises(DesktopInputError) as error:value.input(dict(event='key',vk=65,down=True))
    assert error.value.input_reason=='capture_required' and not value.secure.calls

def test_invalid_service_state_denies_input_without_falling_back_or_losing_video_permission():
    value=backend()
    def invalid_state():raise ValueError('Invalid state response')
    value.secure.input_state=invalid_state
    with pytest.raises(DesktopInputError) as error:value.input(dict(event='move',x=.5,y=.5))
    assert error.value.input_backend=='service' and error.value.input_reason=='service_unavailable'
    assert value.secure.authorized and not [c for c in value.secure.calls if c[0]=='input']

def test_monitor_switch_releases_held_service_input_before_repriming():
    value=backend();value.input(dict(event='button',button='left',down=True,x=.5,y=.5))
    value.capture_monitor=2;value.rect=dict(RECT,left=-1920);value.virtual_rect=dict(RECT,left=-1920,width=3840)
    value.secure.rect=value.rect.copy();value.secure.virtual=value.virtual_rect.copy()
    start=len(value.secure.calls);value.input(dict(event='move',x=.2,y=.3))
    assert [c[0] for c in value.secure.calls[start:]]==['release','capture','input']

def test_service_installed_after_gui_start_is_loaded_in_an_approved_lease():
    config=[None];opened=[]
    class Pipe:
        def __init__(self,c):opened.append(c)
        def exchange(self,p,timeout):return b'\0\0'
        def close(self):pass
    broker=BrokerClient(Pipe,configuration_loader=lambda:config[0])
    broker.begin_session();assert not broker.available() and not opened
    config[0]={'fixture':'installed'}
    assert broker.available() and opened==[config[0]]
    broker.end_session();assert not broker.available()

def test_new_approved_session_refreshes_administrator_binding():
    config=[{'fixture':1}];opened=[]
    class Pipe:
        def __init__(self,c):opened.append(c.copy())
        def exchange(self,p,timeout):return b'\0\0'
        def close(self):pass
    broker=BrokerClient(Pipe,configuration_loader=lambda:config[0]);broker.begin_session();assert broker.available()
    broker.end_session();config[0]={'fixture':2};broker.begin_session();assert broker.available()
    assert opened==[{'fixture':1},{'fixture':2}]

def test_late_capture_from_previous_lease_is_rejected_after_reauthorization():
    entered=threading.Event();resume=threading.Event();errors=[]
    class Pipe:
        def __init__(self,c):pass
        def exchange(self,p,timeout):entered.set();resume.wait(2);return b'\0\0'
        def close(self):pass
    broker=BrokerClient(Pipe,{'fixture':True});broker.begin_session()
    def request():
        try:broker._request(b'\x01')
        except OSError:errors.append('old lease rejected')
    thread=threading.Thread(target=request);thread.start();assert entered.wait(1)
    broker.end_session();broker.begin_session();resume.set();thread.join(1)
    assert not thread.is_alive() and errors==['old lease rejected']
    broker.end_session()

def test_control_error_reports_only_bounded_code_and_reason_not_exception_or_input():
    from novoacesso.session import Peer
    messages=[]
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def control(self,value):messages.append(value)
        def close(self):self.closed.set()
    def fail(value):raise DesktopInputError(87)
    peer=Peer(Channel(),'host',lambda *a:None,lambda *a:None,{'control':True},SimpleNamespace(input=fail,release=lambda:None))
    try:
        peer.apply_input(dict(event='key',vk=65,down=True,private_marker='never log this'))
        assert messages[-1]['diagnostic']==dict(code=87,backend='windows',reason='input_rejected')
        assert 'never log this' not in json.dumps(messages) and not peer.closed.is_set()
    finally:peer.close()
