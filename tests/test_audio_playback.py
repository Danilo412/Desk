import queue
import threading
import zlib
from types import SimpleNamespace
import numpy as np
import pytest
from novoacesso.audio import receive_audio,FRAMES,CHANNELS,capture_loop
from novoacesso.audio_backend import write_wasapi
from novoacesso.wire import ProtocolError


class RenderBuffer:
    channelmap=[0,1]
    def __init__(self,available):
        self.available=iter(available);self.released=[];self.output=[];self.current=None
    def _render_available_frames(self):return next(self.available)
    def _render_buffer(self,count):
        self.current=bytearray(b'\xff'*(count*2*4));return [self.current]
    def _render_release(self,count):
        assert len(self.current)==count*2*4
        self.released.append(count);self.output.append(bytes(self.current))


class ExactCopy:
    @staticmethod
    def memmove(destination,source,count):
        # Releasing anything beyond this copy would replay stale/uninitialized
        # samples. Fail at the boundary rather than reproducing loop internals.
        assert len(destination)==len(source)==count
        destination[:]=source


@pytest.mark.parametrize('available,expected',[
    ([3200],[1600]),
    ([1000,3200],[1000,600]),
    ([0,100,0,1400,9000],[100,1400,100]),
])
def test_windows_buffer_never_releases_unwritten_samples(available,expected):
    samples=np.linspace(-.5,.5,3200,dtype=np.float32).reshape(1600,2)
    player=RenderBuffer(available)
    write_wasapi(player,samples,ExactCopy)
    assert player.released==expected
    assert b''.join(player.output)==samples.tobytes()


def test_windows_output_preserves_channel_order_and_can_cancel_full_buffer():
    player=RenderBuffer([9999]);player.channelmap=[1,0]
    samples=np.array([[.1,.2],[.3,.4]],np.float32)
    write_wasapi(player,samples,ExactCopy)
    assert b''.join(player.output)==samples[:,[1,0]].tobytes()
    closed=threading.Event();closed.set()
    player=RenderBuffer([])
    write_wasapi(player,samples,ExactCopy,closed)
    assert player.released==[]


def peer():
    return SimpleNamespace(role='viewer',permissions={'audio':True},audio_queue=queue.Queue(maxsize=4),audio_playback_running=True)


def test_backlogged_audio_keeps_latest_blocks_and_recording_still_receives_all():
    p=peer();recorded=[];p.recording_audio_sink=lambda raw,*args:recorded.append(raw)
    blocks=[bytes([i])*FRAMES*CHANNELS*2 for i in range(6)]
    for raw in blocks:receive_audio(p,zlib.compress(raw))
    assert recorded==blocks
    assert [p.audio_queue.get_nowait() for _ in range(4)]==blocks[-4:]


@pytest.mark.parametrize('raw',[b'',b'\x00',b'\x00'*6])
def test_partial_stereo_frames_are_rejected_before_playback_or_recording(raw):
    p=peer();recorded=[];p.recording_audio_sink=lambda *args:recorded.append(args)
    with pytest.raises(ProtocolError):receive_audio(p,zlib.compress(raw))
    assert p.audio_queue.empty() and not recorded


def test_legacy_100ms_wire_format_stays_compatible_and_rejects_short_packets():
    p=peer()
    raw=b'\0'*(1600*4)
    receive_audio(p,zlib.compress(raw));assert p.audio_queue.get_nowait()==raw
    with pytest.raises(ProtocolError):receive_audio(p,zlib.compress(b'\0'*(320*4)))


def test_loopback_permission_revoked_while_recording_does_not_send(monkeypatch):
    import sys
    p=SimpleNamespace(closed=threading.Event(),permissions={'audio':True},audio_capture_running=True,event=lambda *a:None)
    sent=[];p.channel=SimpleNamespace(send=lambda *a:sent.append(a))
    class Recorder:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def record(self,**kwargs):
            p.permissions['audio']=False
            return np.zeros((1600,2),np.float32)
    loop=SimpleNamespace(isloopback=True,recorder=lambda **kwargs:Recorder())
    fake=SimpleNamespace(default_speaker=lambda:SimpleNamespace(id='out'),get_microphone=lambda *a,**kw:loop)
    monkeypatch.setitem(sys.modules,'soundcard',fake)
    capture_loop(p)
    assert not sent and not p.audio_capture_running
