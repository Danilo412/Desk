import threading,time
from types import SimpleNamespace
import pytest
from novoacesso.session import Peer
from novoacesso.wire import ProtocolError
from novoacesso.remote_features import validate_stroke

class Channel:
    def __init__(self):self.messages=[];self.io_thread=None
    def control(self,value):self.messages.append(value)
    def close(self):pass

def host(request,control=True):
    channel=Channel();events=[]
    peer=Peer(channel,'host',lambda k,d:events.append((k,d)),request,dict(control=control),backend=SimpleNamespace(release=lambda:None),monitors=[{},{}])
    return peer,channel,events

def wait(predicate):
    end=time.monotonic()+2
    while not predicate() and time.monotonic()<end:time.sleep(.01)
    assert predicate()

def test_restart_is_not_requested_without_control_and_decline_grants_nothing():
    calls=[];peer,channel,events=host(lambda *a:calls.append(a) or True,control=False)
    peer.features.handle(dict(type='advanced_request',id='a'*16,operation='restart'));wait(lambda:channel.messages)
    assert calls==[] and channel.messages[-1]['status']=='declined'
    peer.close()
    peer,channel,events=host(lambda *a:False)
    peer.features.handle(dict(type='advanced_request',id='b'*16,operation='whiteboard'));wait(lambda:channel.messages)
    assert channel.messages[-1]['status']=='declined' and not peer.features.whiteboard_allowed;peer.close()

def test_info_is_sent_only_after_approval_and_disconnect_cancels(monkeypatch):
    from novoacesso import remote_features
    monkeypatch.setattr(remote_features,'system_information',lambda monitors:{'Sistema':'Windows de teste'})
    peer,channel,events=host(lambda *a:True)
    peer.features.handle(dict(type='advanced_request',id='c'*16,operation='system_info'));wait(lambda:channel.messages)
    assert channel.messages[-1]['values']=={'Sistema':'Windows de teste'};peer.close()
    peer,channel,events=host(lambda *a:peer.closed.set() or True)
    peer.features.handle(dict(type='advanced_request',id='d'*16,operation='whiteboard'));wait(lambda:not peer.features.busy)
    assert not peer.features.whiteboard_allowed and not channel.messages

def test_annotation_validation_permission_and_revocation():
    stroke=dict(shape='arrow',color='#ef443b',width=3,points=[[0,0],[1,1]])
    peer,channel,events=host(lambda *a:True)
    peer.features.handle(dict(type='annotation',action='stroke',stroke=stroke));assert events==[]
    peer.features.whiteboard_allowed=True;peer.features.handle(dict(type='annotation',action='stroke',stroke=stroke));assert events[-1][0]=='annotation'
    peer.set_permissions({'control':False});assert not peer.features.whiteboard_allowed
    count=sum(k=='annotation' for k,d in events);peer.features.handle(dict(type='annotation',action='stroke',stroke=stroke));assert sum(k=='annotation' for k,d in events)==count
    with pytest.raises(ProtocolError):validate_stroke(dict(stroke,points=[[float('nan'),0],[1,1]]))
    with pytest.raises(ProtocolError):validate_stroke(dict(stroke,points=[[0,0]]*513))
    peer.close()

def test_print_only_sends_locally_selected_supported_file(tmp_path):
    path=tmp_path/'documento.pdf';path.write_bytes(b'%PDF-test')
    peer,channel,events=host(lambda *a:str(path));sent=[];peer.send_file=sent.append
    peer.features.handle(dict(type='advanced_request',id='e'*16,operation='print'));wait(lambda:channel.messages)
    assert sent==[path] and channel.messages[-1]['status']=='accepted' and 'path' not in str(channel.messages[-1]);peer.close()
