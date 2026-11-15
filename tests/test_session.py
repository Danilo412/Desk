from contextlib import nullcontext
import base64
import json
from pathlib import Path
import queue
import secrets
import threading
import time
import pytest
from PIL import Image
from novoacesso.session import HostService,join
from novoacesso.wire import ProtocolError,connect_invitation,parse_invitation

def wait_for(predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.02)
    raise AssertionError('Evento esperado não chegou dentro do prazo.')

class FakeDesktop:
    def __init__(self):self.inputs=[];self.released=0;self.counter=0
    def monitors(self):return [dict(left=0,top=0,width=128,height=128),dict(left=0,top=0,width=128,height=128)]
    def capture_source(self):return nullcontext()
    def capture(self,source,index,width):
        self.counter+=1
        return Image.new('RGB',(128,128),(self.counter*5%255,80,120))
    def input(self,data):self.inputs.append(data)
    def release(self):self.released+=1

@pytest.fixture
def session(tmp_path):
    backend=FakeDesktop();events=[];viewer_events=[];consents=[]
    def request(kind,data,timeout):
        if kind=='consent':consents.append(data);return True
        if kind=='save_file':return str(tmp_path/data['name'])
    host=HostService(backend,lambda k,d:events.append((k,d)),request,dict(control=False,clipboard=False,audio=False))
    token=host.start('127.0.0.1')
    viewer=join(token,lambda k,d:viewer_events.append((k,d)),request);viewer.start()
    wait_for(lambda:host.peer)
    yield host,viewer,backend,events,viewer_events,tmp_path,token,consents
    viewer.close();host.stop()
    for worker in viewer.workers+host.peer.workers:worker.join(timeout=1)

def test_tls_screen_chat_and_permission_revocation(session):
    host,viewer,backend,events,received,*_=session
    wait_for(lambda:any(k=='frame' for k,d in received))
    assert viewer.channel.sock.version()=='TLSv1.3'
    viewer.send(dict(type='chat',text='Olá, conexão própria.'))
    wait_for(lambda:any(k=='chat' and d['text']=='Olá, conexão própria.' for k,d in events))
    viewer.send(dict(type='input',event='key',vk=65,down=True));time.sleep(.1)
    assert backend.inputs==[]
    host.peer.set_permissions(dict(control=True,clipboard=True))
    wait_for(lambda:viewer.permissions.get('control'))
    viewer.send(dict(type='input',event='key',vk=65,down=True))
    wait_for(lambda:backend.inputs)
    viewer.send(dict(type='clipboard',text='texto autorizado'))
    wait_for(lambda:any(k=='clipboard' and d['text']=='texto autorizado' for k,d in events))
    host.peer.set_permissions(dict(control=False,clipboard=False))
    wait_for(lambda:not viewer.permissions.get('control'))
    assert backend.released>=1
    length=len(backend.inputs)
    viewer.send(dict(type='input',event='key',vk=66,down=True));time.sleep(.1)
    assert len(backend.inputs)==length

def test_file_transfer_with_consent_and_sha256(session,tmp_path):
    host,viewer,backend,events,received,destination,*_=session
    source=tmp_path/'source';source.mkdir()
    file=source/'arquivo-teste.bin';content=secrets.token_bytes(200123);file.write_bytes(content)
    viewer.send_file(file)
    result=destination/file.name
    wait_for(lambda:result.exists())
    assert result.read_bytes()==content
    assert not list(destination.glob('.novoacesso-*.part'))

def test_unrequested_file_chunk_ends_session(session):
    host,viewer,*_=session
    viewer.channel.send(b'F',b'0123456789abcdef'+b'not approved')
    wait_for(lambda:host.peer.closed.is_set())

def test_invitation_single_use_and_automatic_vp8(session):
    host,viewer,backend,events,received,tmp_path,token,consents=session
    assert len(consents)==1
    with pytest.raises((OSError,ConnectionError)):join(token,lambda *a:None,lambda *a:True)
    # Every frame must contain visible motion. A five-level color ramp only
    # exceeded the pipeline's motion threshold on wraparound, so a stats sample
    # could miss its short VP8 interval depending on the runner's scheduling.
    def moving_capture(source,index,width):
        backend.counter+=1
        return Image.new('RGB',(128,128),(255 if backend.counter%2 else 0,80,120))
    backend.capture=moving_capture
    wait_for(lambda:any(k=='stats' and d['vp8']>0 for k,d in events),timeout=7)

def test_denied_consent_sends_no_screen():
    backend=FakeDesktop();asked=[]
    def deny(kind,data,timeout):asked.append(kind);return False
    host=HostService(backend,lambda *a:None,deny,dict(control=False,clipboard=False,audio=False))
    token=host.start('127.0.0.1')
    try:
        with pytest.raises((OSError,ConnectionError)):join(token,lambda *a:None,deny)
        assert asked==['consent'] and backend.counter==0
    finally:host.stop()

def test_bad_certificate_and_bad_secret_never_reach_consent():
    backend=FakeDesktop();asked=[]
    host=HostService(backend,lambda *a:None,lambda *a:asked.append(a),dict(control=False,clipboard=False,audio=False))
    token=host.start('127.0.0.1')
    def encode(data):return 'NA1-'+base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
    try:
        data=parse_invitation(token);data['fp']='00'*32
        with pytest.raises(ProtocolError):connect_invitation(encode(data))
        data=parse_invitation(token);data['secret']='a'*43
        with pytest.raises((OSError,ConnectionError)):join(encode(data),lambda *a:None,lambda *a:True)
        assert not asked and backend.counter==0
    finally:host.stop()
