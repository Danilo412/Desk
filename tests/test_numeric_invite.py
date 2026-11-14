import asyncio,json,threading,time
from collections import defaultdict
import pytest
from metered_realtime import Direct,Presence
from metered_realtime.protocol.types import PresencePeer
from novoacesso.numeric_invite import NumericInvite,resolve_code,normalize_code
from novoacesso.wire import make_invitation,ProtocolError

class Hub:
    def __init__(self):self.clients={};self.rooms=defaultdict(set);self.lock=threading.RLock();self.messages=[];self.seq=0
    def client(self,**kwargs):return Client(self)

class Client:
    def __init__(self,hub):self.hub=hub;self.handlers=defaultdict(list);self.loop=None;self.id=None
    def on(self,kind):
        def register(fn):self.handlers[kind].append(fn);return fn
        return register
    def deliver(self,event):
        def invoke():
            for fn in self.handlers[type(event)]:
                result=fn(event)
                if asyncio.iscoroutine(result):asyncio.create_task(result)
        self.loop.call_soon_threadsafe(invoke)
    async def connect(self):
        self.loop=asyncio.get_running_loop()
        with self.hub.lock:
            self.hub.seq+=1;self.id=str(self.hub.seq);self.hub.clients[self.id]=self
    async def subscribe(self,room):
        with self.hub.lock:
            old=list(self.hub.rooms[room]);self.hub.rooms[room].add(self.id)
            self.deliver(Presence(room,tuple(PresencePeer(peer_id=p) for p in old),()))
            for peer in old:self.hub.clients[peer].deliver(Presence(room,(PresencePeer(peer_id=self.id),),()))
    async def send(self,to,data):
        with self.hub.lock:
            self.hub.messages.append(data)
            if to in self.hub.clients:self.hub.clients[to].deliver(Direct(self.id,data))
    async def close(self):
        with self.hub.lock:
            self.hub.clients.pop(self.id,None)
            for members in self.hub.rooms.values():members.discard(self.id)

def test_numeric_roundtrip_encrypted_and_stop():
    hub=Hub();ready=threading.Event();events=[]
    _,token=make_invitation('127.0.0.1',4433,'ab'*32)
    def event(kind,data):events.append((kind,data));ready.set()
    host=NumericInvite(token,'pk_live_'+'a'*32,event,hub.client).start()
    try:
        assert ready.wait(5) and events[0][0]=='numeric_ready'
        displayed=events[0][1]['code']
        assert len(displayed)==14 and normalize_code(displayed)==host.code
        assert resolve_code(displayed,host.key,timeout=3,client_factory=hub.client)==token
        assert token not in json.dumps(hub.messages)
        assert any(item.get('sealed') for item in hub.messages)
    finally:host.stop();host.thread.join(5)
    assert not host.thread.is_alive() and not hub.clients
    with pytest.raises(ProtocolError,match='não encontrado'):
        resolve_code(displayed,host.key,timeout=.25,client_factory=hub.client)

def test_rejects_bad_code_and_expired_invitation():
    for code in ('123456','abcdefghijkl','１２３４５６７８９０１２'):
        with pytest.raises(ProtocolError):normalize_code(code)
    _,token=make_invitation('127.0.0.1',4433,'ab'*32,lifetime=-1)
    with pytest.raises(ProtocolError):NumericInvite(token,'key',lambda *a:None)
    with pytest.raises(ProtocolError):NumericInvite('NAU1-test','key',lambda *a:None)
