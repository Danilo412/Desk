"""Ordered input channel, authenticated by keys exchanged in the approved TLS session.

Mouse/key traffic does not wait behind decoded video or file records. This
channel never grants permission: every message passes the host's normal gate.
"""
import json,queue,secrets,threading
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

CAPABILITY='input_channel_v1'
AAD=b'Desk ordered input v1'

class InputCipher:
    def __init__(self,key,prefix):
        if len(key)!=32 or len(prefix)!=4:raise ValueError('Chave de controle inválida.')
        self.aead=ChaCha20Poly1305(key);self.prefix=prefix;self.counter=0;self.highest=-1
    def seal(self,value):
        if self.counter>=2**64:raise ValueError('Limite do canal de controle atingido.')
        raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>512:raise ValueError('Entrada fora dos limites.')
        number=self.counter.to_bytes(8,'big');self.counter+=1
        return number+self.aead.encrypt(self.prefix+number,raw,AAD)
    def open(self,packet):
        if not isinstance(packet,bytes) or not 24<len(packet)<=536:return None
        number=int.from_bytes(packet[:8],'big')
        if number<=self.highest:return None
        try:
            raw=self.aead.decrypt(self.prefix+packet[:8],packet[8:],AAD)
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('type')!='input':return None
        except Exception:return None
        self.highest=number;return value

class FastInput:
    def __init__(self,peer):
        self.peer=peer;self.outer=getattr(getattr(peer.channel,'sock',None),'outer',None)
        self.sender=None;self.receiver=None;self.ready=threading.Event();self.negotiating=False
        self.queue=queue.Queue(maxsize=128);self.active=False;self.sent=0;self.received=0
    def negotiate(self):
        if self.negotiating or self.peer.role!='viewer' or CAPABILITY not in self.peer.remote_media:return
        if not self.peer.permissions.get('control') or not callable(getattr(self.outer,'open_input_channel',None)):return
        self.negotiating=True;self.peer.spawn(self._prepare)
    def _prepare(self):
        if self.peer.closed.is_set() or not self.outer.open_input_channel():return
        # Wait at a TLS ordering barrier before switching the input route.
        with self.peer.input_route_lock:
            if self.peer.closed.is_set():return
            key=secrets.token_bytes(32);prefix=secrets.token_bytes(4);self.sender=InputCipher(key,prefix)
            self.peer.send(dict(type='input_route',key=key.hex(),prefix=prefix.hex()))
            if not self.ready.wait(2):self.sender=None;self.ready.clear()
    def handle(self,msg):
        if CAPABILITY not in self.peer.remote_media or self.peer.closed.is_set():return
        if msg['type']=='input_route_ready':
            if self.peer.role=='viewer' and self.sender:self.ready.set()
            return
        if self.peer.role!='host' or not self.peer.permissions.get('control') or self.outer is None or self.receiver:return
        key,prefix=msg.get('key'),msg.get('prefix')
        if not isinstance(key,str) or not isinstance(prefix,str) or len(key)!=64 or len(prefix)!=8:return
        try:self.receiver=InputCipher(bytes.fromhex(key),bytes.fromhex(prefix))
        except ValueError:return
        self.outer.input_handler=self.enqueue;self.peer.spawn(self.receive)
        self.peer.send(dict(type='input_route_ready'))
    def send(self,value):
        if not self.ready.is_set():return False
        if self.peer.closed.is_set():return True
        try:accepted=self.outer.send_input_packet(self.sender.seal(value))
        except Exception:accepted=False
        if not accepted:self.peer.close('O canal de controle foi interrompido. Reconecte para continuar.')
        else:self.active=True;self.sent+=1
        # Once switched, do not race older RTC events with a TLS fallback.
        return True
    def enqueue(self,packet):
        if self.peer.closed.is_set():return
        try:self.queue.put_nowait(packet)
        except queue.Full:self.peer.close('O canal de controle excedeu a fila permitida.')
    def receive(self):
        while not self.peer.closed.is_set():
            try:packet=self.queue.get(timeout=.1)
            except queue.Empty:continue
            receiver=self.receiver
            if not receiver:continue
            value=receiver.open(packet)
            if value is None:continue
            self.received+=1;self.active=True;self.peer.input_dispatch.put(value)
    def stop(self):
        if self.outer and getattr(self.outer,'input_handler',None)==self.enqueue:self.outer.input_handler=None
        self.sender=None;self.receiver=None;self.ready.clear()
