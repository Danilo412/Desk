import queue
import threading
import zlib
from types import SimpleNamespace
import pytest
from novoacesso.audio import receive_audio,capture_loop,RATE,FRAMES,CHANNELS
from novoacesso.codec import bounded_inflate
from novoacesso.wire import ProtocolError

def test_audio_block_validation_and_permission_gate():
    peer=SimpleNamespace(role='viewer',permissions={'audio':False},audio_queue=queue.Queue(maxsize=4),audio_playback_running=True)
    raw=b'\0'*(FRAMES*CHANNELS*2)
    receive_audio(peer,zlib.compress(raw))
    assert peer.audio_queue.empty()
    peer.permissions['audio']=True
    receive_audio(peer,zlib.compress(raw));assert peer.audio_queue.get_nowait()==raw
    with pytest.raises(ProtocolError):receive_audio(peer,zlib.compress(raw+b'bad'))

def test_loopback_capture_encodes_pcm_and_never_falls_back_to_mic(monkeypatch):
    import sys,numpy as np
    calls=[];packets=[];closed=threading.Event()
    class Recorder:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def record(self,**kwargs):return np.zeros((FRAMES,CHANNELS),np.float32)
    class Loopback:
        isloopback=True
        def recorder(self,**kwargs):calls.append(kwargs);return Recorder()
    def get_microphone(speaker_id,include_loopback):
        assert speaker_id=='test-output' and include_loopback is True
        return Loopback()
    fake=SimpleNamespace(default_speaker=lambda:SimpleNamespace(id='test-output'),get_microphone=get_microphone)
    monkeypatch.setitem(sys.modules,'soundcard',fake)
    def send(kind,data):packets.append((kind,data));closed.set()
    peer=SimpleNamespace(closed=closed,permissions={'audio':True},audio_capture_running=True,
        channel=SimpleNamespace(send=send),event=lambda *a:None)
    capture_loop(peer)
    assert calls[0]['samplerate']==RATE and calls[0]['channels']==2
    assert packets[0][0]==b'A' and bounded_inflate(packets[0][1],FRAMES*CHANNELS*2)==b'\0'*(FRAMES*CHANNELS*2)
    assert not peer.audio_capture_running

def test_file_integrity_failure_does_not_replace_destination(tmp_path):
    import hashlib,socket
    from novoacesso.session import Peer
    from novoacesso.wire import Channel
    left,right=socket.socketpair()
    destination=tmp_path/'destino.txt';destination.write_text('conteúdo anterior')
    peer=Peer(Channel(left),'viewer',lambda *a:None,lambda *a:str(destination),{'control':False})
    try:
        peer._file_offer(dict(id='0123456789abcdef',name='../destino.txt',size=3,sha256=hashlib.sha256(b'yes').hexdigest()))
        peer._file_chunk(b'0123456789abcdef'+b'bad')
        with pytest.raises(ProtocolError):peer._file_end(dict(id='0123456789abcdef'))
        assert destination.read_text()=='conteúdo anterior'
        assert not list(tmp_path.glob('.novoacesso-*.part'))
    finally:peer.close();right.close()
