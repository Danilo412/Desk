"""Optional low-delay audio, bound to the approved TLS session by an AEAD key.

Only media uses the unordered, non-retransmitting RTC channel. The random key
and nonce prefix are exchanged inside authenticated TLS after audio consent.
No keys are persisted; closing the peer removes the callback and key objects.
"""
import queue,secrets,struct,threading
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag

CAPABILITY='audio_fast_v1'
AAD=b'Desk audio v1'
COUNTER=struct.Struct('>Q')

class AudioCipher:
    def __init__(self,key,prefix):
        if len(key)!=32 or len(prefix)!=4:raise ValueError('Chave de áudio inválida.')
        self.aead=ChaCha20Poly1305(key);self.prefix=prefix;self.counter=0;self.highest=-1
    def seal(self,payload):
        if self.counter>=2**64:raise ValueError('Limite do transporte de áudio atingido.')
        counter=COUNTER.pack(self.counter);self.counter+=1
        return counter+self.aead.encrypt(self.prefix+counter,payload,AAD)
    def open(self,packet):
        if not isinstance(packet,bytes) or not 24<len(packet)<=1400:return None
        counter=COUNTER.unpack_from(packet)[0]
        if counter<=self.highest:return None
        try:payload=self.aead.decrypt(self.prefix+packet[:8],packet[8:],AAD)
        except InvalidTag:return None
        self.highest=counter;return payload

class FastAudio:
    def __init__(self,peer):
        self.peer=peer;self.outer=getattr(peer.channel.sock,'outer',None) if hasattr(peer.channel,'sock') else None
        self.sender=None;self.receiver=None;self.ready=threading.Event();self.queue=queue.Queue(maxsize=32);self.started=False
        self.sent=0;self.received=0;self.rejected=0
    def prepare_send(self):
        if self.sender:return self.ready.is_set()
        if CAPABILITY not in self.peer.remote_media or not callable(getattr(self.outer,'open_audio_channel',None)):return False
        if not self.outer.open_audio_channel():return False
        key=secrets.token_bytes(32);prefix=secrets.token_bytes(4);self.sender=AudioCipher(key,prefix)
        self.peer.send(dict(type='audio_route',key=key.hex(),prefix=prefix.hex()))
        return self.ready.wait(2) and not self.peer.closed.is_set()
    def send(self,payload):
        if not self.sender or not self.ready.is_set() or not self.peer.permissions.get('audio') or self.peer.closed.is_set():return False
        if self.outer.send_datagram(self.sender.seal(payload)):self.sent+=1;return True
        return False
    def handle(self,msg):
        if CAPABILITY not in self.peer.remote_media:return
        if msg['type']=='audio_route_ready':
            if self.peer.role=='host' and self.sender:self.ready.set()
            return
        if self.peer.role!='viewer' or not self.peer.permissions.get('audio') or self.outer is None:return
        key,prefix=msg.get('key'),msg.get('prefix')
        if not isinstance(key,str) or not isinstance(prefix,str) or len(key)!=64 or len(prefix)!=8:return
        if self.receiver:return
        try:self.receiver=AudioCipher(bytes.fromhex(key),bytes.fromhex(prefix))
        except ValueError:return
        self.outer.datagram_handler=self.enqueue
        if not self.started:self.started=True;self.peer.spawn(self.receive)
        self.peer.send(dict(type='audio_route_ready'))
    def enqueue(self,data):
        if self.peer.closed.is_set() or not self.peer.permissions.get('audio'):return
        try:self.queue.put_nowait(data)
        except queue.Full:
            try:self.queue.get_nowait()
            except queue.Empty:pass
            try:self.queue.put_nowait(data)
            except queue.Full:pass
    def receive(self):
        from .audio import receive_audio
        while not self.peer.closed.is_set():
            try:packet=self.queue.get(timeout=.1)
            except queue.Empty:continue
            receiver=self.receiver
            if self.peer.closed.is_set() or not self.peer.permissions.get('audio') or not receiver:continue
            payload=receiver.open(packet)
            if payload is None:self.rejected+=1;continue
            self.received+=1
            try:
                with self.peer.audio_decode_lock:receive_audio(self.peer,payload)
            except Exception:self.rejected+=1
    def stop(self):
        if self.outer is not None and getattr(self.outer,'datagram_handler',None)==self.enqueue:self.outer.datagram_handler=None
        self.sender=None;self.receiver=None;self.ready.clear()
