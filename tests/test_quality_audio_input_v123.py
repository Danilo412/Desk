import ctypes,queue,threading,time
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPointF,QEvent,Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from novoacesso.audio_codec import OpusEncoder,OpusDecoder,AudioPlayout,CAPABILITY,FRAMES,RATE
from novoacesso.audio import receive_audio
from novoacesso.video_pipeline import ScreenPipeline,VideoDecoder
from novoacesso.codec import ScreenDecoder
from novoacesso.input_dispatch import InputDispatcher
from novoacesso.desktop import DesktopBackend,NativeInput
from novoacesso.app import RemoteCanvas
from novoacesso.wire import ProtocolError

def test_slow_video_decode_does_not_block_audio_or_chat():
    import zlib
    from novoacesso.session import Peer
    messages=queue.Queue();decoding=threading.Event();resume=threading.Event();chat=threading.Event()
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def control(self,value):pass
        def receive(self):return messages.get(timeout=2)
        def close(self):self.closed.set()
    peer=Peer(Channel(),'viewer',lambda kind,data:chat.set() if kind=='chat' else None,lambda *args:None,{'audio':True})
    def decode(data):decoding.set();resume.wait(2);return Image.new('RGB',(64,64))
    peer.decoder=SimpleNamespace(decode=decode);peer.audio_playback_running=True
    try:
        peer.spawn(peer._decode_video);peer.spawn(peer._receive)
        messages.put((b'V',b'\0'*8));assert decoding.wait(1)
        messages.put((b'A',zlib.compress(b'\0'*6400)));messages.put((b'J',dict(type='chat',text='teste')))
        assert chat.wait(.5) and not peer.audio_queue.empty()
    finally:
        resume.set();peer.close();messages.put((b'J',dict(type='bye')));peer.wait_for_workers()

def test_opus_retains_high_frequencies_stereo_and_recording_rate():
    encoder=OpusEncoder();captured=[]
    peer=SimpleNamespace(role='viewer',permissions={'audio':True},remote_media={CAPABILITY},audio_queue=queue.Queue(maxsize=12),audio_playback_running=True,recording_audio_sink=lambda raw,rate,channels:captured.append((raw,rate,channels)))
    for i in range(50):
        t=(np.arange(FRAMES)+i*FRAMES)/RATE
        samples=np.column_stack((.3*np.sin(2*np.pi*12000*t),.3*np.sin(2*np.pi*3500*t)))
        receive_audio(peer,encoder.encode(samples))
    assert len(captured)==50 and all(rate==48000 and channels==2 and len(raw)==3840 for raw,rate,channels in captured)
    assert peer.audio_queue.qsize()==12
    decoded=np.frombuffer(b''.join(raw for raw,_,_ in captured),'<i2').reshape(-1,2)[2000:]
    for channel,hz in [(0,12000),(1,3500)]:
        spectrum=np.abs(np.fft.rfft(decoded[:,channel]*np.hanning(len(decoded))))
        found=np.fft.rfftfreq(len(decoded),1/RATE)[np.argmax(spectrum)]
        assert abs(found-hz)<10 and np.sqrt(np.mean(decoded[:,channel].astype(float)**2))>3000

def test_opus_rejects_unauthorized_unnegotiated_and_malformed_audio():
    packet=OpusEncoder().encode(np.zeros((FRAMES,2)))
    peer=SimpleNamespace(role='viewer',permissions={'audio':False},remote_media={CAPABILITY})
    receive_audio(peer,packet);assert not hasattr(peer,'opus_decoder')
    peer.permissions['audio']=True;peer.remote_media=set()
    with pytest.raises(ProtocolError):receive_audio(peer,packet)
    decoder=OpusDecoder()
    with pytest.raises(ProtocolError):decoder.decode(packet[:5])
    decoder.decode(packet)
    invalid=bytearray(packet);invalid[0]=0
    with pytest.raises(ProtocolError):decoder.decode(bytes(invalid))

def test_audio_permission_toggle_can_resume_after_skipped_packets():
    encoder=OpusEncoder();peer=SimpleNamespace(role='viewer',permissions={'audio':True},remote_media={CAPABILITY},audio_queue=queue.Queue(maxsize=24),audio_playback_running=True)
    samples=np.zeros((FRAMES,2))
    receive_audio(peer,encoder.encode(samples));peer.permissions['audio']=False
    for _ in range(4):receive_audio(peer,encoder.encode(samples))
    assert peer.audio_queue.qsize()==1
    peer.permissions['audio']=True;receive_audio(peer,encoder.encode(samples))
    assert peer.audio_queue.qsize()==2

def test_playout_absorbs_short_jitter_and_bounds_stale_audio():
    playout=AudioPlayout();tone=np.ones((960,2),np.float32)*.25
    assert playout.take() is None
    for _ in range(6):playout.push(tone)
    for i in range(20):
        # Two delayed packets arrive together, after a 40 ms interruption.
        if i!=5:
            playout.push(tone)
            if i==6:playout.push(tone)
        samples=playout.take();assert samples.shape==(960,2) and np.isfinite(samples).all()
    assert playout.underruns==0
    for _ in range(30):playout.push(tone)
    assert len(playout.buffer)<=19200 and playout.dropped>0
    while len(playout.buffer)>=960:playout.take()
    tail=playout.take();assert playout.underruns==1 and np.max(np.abs(np.diff(tail[:,0])))<.01

def test_video_uses_real_elapsed_pts_and_preserves_encoder_across_restoration():
    pipeline=ScreenPipeline();video=VideoDecoder();tiles=ScreenDecoder()
    image=Image.new('RGB',(640,360),'white')
    _,packet,_=pipeline.encode(image,mode='vp8',now=10);video.decode(packet);context=pipeline.video
    pipeline.factor=.35
    image.paste('navy',(0,0,200,200));_,packet,_=pipeline.encode(image,mode='vp8',now=10.1);video.decode(packet)
    assert pipeline.pts==100 and pipeline.video is context
    kind,packet,_=pipeline.encode(image,mode='auto',now=12)
    assert kind==b'V' and tiles.decode(packet).tobytes()==image.tobytes()
    image.paste('green',(0,0,200,200));kind,packet,_=pipeline.encode(image,mode='vp8',now=13)
    assert kind==b'W' and pipeline.video is context and video.decode(packet).size==image.size and pipeline.pts==3000

def test_pointer_final_move_is_sent_after_throttled_burst_and_focus_loss_cancels():
    canvas=RemoteCanvas();canvas.resize(640,360);canvas.set_frame(Image.new('RGB',(640,360)));canvas.allow_control=True;canvas.show();QTest.qWait(30)
    events=[];canvas.input_event.connect(events.append)
    def move(x):
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(x,100),QPointF(x,100),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas,event)
    try:
        move(100);move(101);move(140);QTest.qWait(25)
        assert abs([e for e in events if e['event']=='move'][-1]['x']-140/640)<.01
        move(180);canvas.clearFocus();QTest.qWait(20)
        assert canvas.pending_move is None
    finally:canvas.close()

def test_backpressure_does_not_block_gui_or_reorder_buttons():
    entered=threading.Event();resume=threading.Event();closed=threading.Event();values=[]
    def send(value):
        if not entered.is_set():entered.set();resume.wait(2)
        values.append(value)
    dispatcher=InputDispatcher(send,closed,lambda:True,lambda reason:pytest.fail(reason))
    try:
        dispatcher.put(dict(event='move',x=0,y=0));assert entered.wait(1)
        start=time.monotonic()
        for i in range(100):dispatcher.put(dict(event='move',x=i/100,y=0))
        dispatcher.put(dict(event='button',button='left',down=True,x=.99,y=0))
        dispatcher.put(dict(event='move',x=.8,y=.3));dispatcher.put(dict(event='button',button='left',down=False,x=.8,y=.3))
        assert time.monotonic()-start<.05
        resume.set();deadline=time.monotonic()+2
        while len(values)<5 and time.monotonic()<deadline:time.sleep(.005)
        assert [v['event'] for v in values]==['move','move','button','move','button'] and values[1]['x']==.99
    finally:closed.set();resume.set();dispatcher.stop();dispatcher.thread.join(2)

def test_native_input_combines_position_button_and_virtual_desktop_coordinates():
    events=[]
    class FakeUser:
        def GetSystemMetrics(self,n):return {76:-1920,77:0,78:3840,79:1080}[n]
        def SendInput(self,count,pointer,size):
            events.append(NativeInput.from_buffer_copy(ctypes.string_at(pointer,size)));return count
    backend=DesktopBackend.__new__(DesktopBackend);backend.user=FakeUser();backend.lock=threading.RLock();backend.keys=set();backend.buttons=set()
    backend.rect=dict(left=-1920,top=0,width=1920,height=1080)
    backend.input(dict(event='button',x=1.,y=1.,button='back',down=True))
    assert len(events)==1 and events[0].mi.dwFlags&0xc081==0xc081 and events[0].mi.mouseData==1
    assert 32740<events[0].mi.dx<32780 and events[0].mi.dy==65535
    backend.input(dict(event='key',vk=0xa3,down=True));assert events[-1].ki.dwFlags==1
    backend.release();assert not backend.keys and not backend.buttons
    assert any(e.type==1 and e.ki.dwFlags==3 for e in events)
    assert any(e.type==0 and e.mi.dwFlags&0x100 for e in events)
