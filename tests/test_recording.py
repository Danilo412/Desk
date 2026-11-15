import time
import av,numpy as np
from PIL import Image
from novoacesso.recording import VideoRecorder

def test_mp4_video_audio_pause_and_resolution_change(tmp_path):
    path=tmp_path/'teste com espaço.mp4';recorder=VideoRecorder(path,audio=True).start()
    for i in range(5):
        recorder.offer(Image.new('RGB',(320,180),(i*30,60,150)))
        recorder.offer_audio((np.sin(np.arange(3200)*.1)*1000).astype('<i2').tobytes());time.sleep(.1)
    recorder.pause(True);before=recorder.elapsed;time.sleep(.12)
    assert abs(recorder.elapsed-before)<.01 and not recorder.offer(Image.new('RGB',(64,64),'red'))
    recorder.pause(False);recorder.offer(Image.new('RGB',(480,360),'green'));time.sleep(.12);recorder.stop();assert recorder.wait()
    assert recorder.result['success'] and recorder.result['audio_received_samples']==24000
    with av.open(str(path)) as source:
        assert {s.type for s in source.streams}=={'audio','video'}
        frames=list(source.decode(video=0));assert len(frames)>=5 and all((f.width,f.height)==(320,180) for f in frames)
    assert not list(tmp_path.glob('*.part'))

def test_no_frames_preserves_existing_destination_and_mailbox_is_bounded(tmp_path):
    path=tmp_path/'preservar.mp4';path.write_bytes(b'previous-file')
    recorder=VideoRecorder(path).start();recorder.stop();assert recorder.wait()
    assert not recorder.result['success'] and path.read_bytes()==b'previous-file'
    recorder=VideoRecorder(tmp_path/'bounded.mp4')
    for i in range(100):recorder.offer(Image.new('RGB',(16,16),(i,0,0)))
    assert recorder.latest.getpixel((0,0))==(99,0,0) and len(recorder.audio_queue)==0
    recorder.start();time.sleep(.06);recorder.stop();assert recorder.wait() and recorder.result['success']

def test_permission_gate_precedes_recording_audio_observer():
    import queue,threading,zlib
    from types import SimpleNamespace
    from novoacesso.audio import receive_audio
    calls=[];peer=SimpleNamespace(role='viewer',permissions={'audio':False},audio_queue=queue.Queue(maxsize=4),audio_playback_running=True,recording_audio_sink=lambda *args:calls.append(args))
    payload=zlib.compress(b'\0'*6400);receive_audio(peer,payload);assert calls==[]
    peer.permissions['audio']=True;receive_audio(peer,payload);assert len(calls)==1

def test_local_feed_uses_selected_monitor_and_stops_without_capturing_real_desktop(monkeypatch):
    import sys,threading
    from types import SimpleNamespace
    from novoacesso.recording import LocalRecordingFeed
    offered=[];selected=[];done=threading.Event()
    recorder=SimpleNamespace(audio=False,finished=done,paused=False,max_width=1920,fps=30,offer=lambda image:(offered.append(image),done.set()),stop=done.set)
    class FakeCapture:
        monitors=[dict(width=6,height=2),dict(width=4,height=2)]
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def grab(self,monitor):
            selected.append(monitor)
            return SimpleNamespace(size=(4,2),bgra=bytes([10,20,30,0])*8)
    monkeypatch.setitem(sys.modules,'mss',SimpleNamespace(MSS=FakeCapture))
    feed=LocalRecordingFeed(recorder,1).start()
    assert done.wait(2)
    feed.stop()
    for thread in feed.threads:thread.join(2)
    assert len(feed.threads)==1 and selected==[FakeCapture.monitors[1]]
    assert offered[0].size==(4,2) and offered[0].getpixel((0,0))==(30,20,10)

def test_system_audio_recording_rejects_microphone_fallback(monkeypatch):
    import sys,threading
    from types import SimpleNamespace
    from novoacesso.recording import LocalRecordingFeed
    calls=[];recorder=SimpleNamespace(warning='',finished=threading.Event())
    def candidate(identifier,include_loopback):
        calls.append((identifier,include_loopback))
        return SimpleNamespace(isloopback=False,recorder=lambda **kw:(_ for _ in ()).throw(AssertionError('Microphone must never open')))
    monkeypatch.setitem(sys.modules,'soundcard',SimpleNamespace(default_speaker=lambda:SimpleNamespace(id='output-device'),get_microphone=candidate))
    LocalRecordingFeed(recorder)._audio()
    assert calls==[('output-device',True)] and 'Loopback indisponível' in recorder.warning

def test_audio_burst_after_resume_does_not_shift_later_tone(tmp_path):
    def tone(hz):
        samples=(np.sin(2*np.pi*hz*np.arange(1600)/16000)*7000).astype('<i2')
        return np.column_stack((samples,samples)).tobytes()
    recorder=VideoRecorder(tmp_path/'burst.mp4',audio=True).start()
    recorder.offer(Image.new('RGB',(64,36),'navy'))
    for _ in range(5):recorder.offer_audio(tone(440));time.sleep(.1)
    recorder.pause(True);time.sleep(.2);recorder.pause(False);resume=recorder.elapsed
    for _ in range(6):recorder.offer_audio(tone(440))
    time.sleep(.1)
    for _ in range(7):recorder.offer_audio(tone(660));time.sleep(.1)
    recorder.stop();assert recorder.wait() and recorder.result['success']
    chunks=[]
    with av.open(str(tmp_path/'burst.mp4')) as source:
        rate=source.streams.audio[0].rate
        previous=-1
        for frame in source.decode(audio=0):
            assert float(frame.time)>previous;previous=float(frame.time);chunks.append(frame.to_ndarray().mean(axis=0))
    samples=np.concatenate(chunks);first=None
    size=rate//10
    for offset in range(int(resume*rate),len(samples)-size,rate//50):
        spectrum=np.abs(np.fft.rfft(samples[offset:offset+size]*np.hanning(size)))
        hz=np.fft.rfftfreq(size,1/rate)[int(np.argmax(spectrum))]
        if abs(hz-660)<8:first=(offset+size//2)/rate;break
    assert first is not None and first-resume<.4
