import queue,struct
import pytest
from PIL import Image
from novoacesso.multiplex import Outgoing,Incoming,META
from novoacesso.wire import ProtocolError,MAX_RECORD,MAX_CONTROL
from novoacesso.adaptive import AdaptiveQuality
from novoacesso.video_pipeline import ScreenPipeline,VideoDecoder
from novoacesso.codec import ScreenDecoder

def record(kind,payload):return kind+struct.pack('>I',len(payload))+payload

def test_input_preempts_large_frame_and_file_end_stays_ordered():
    out=Outgoing();incoming=Incoming(MAX_RECORD,MAX_CONTROL,ProtocolError)
    out.put(record(b'V',b'v'*200000));out.put(record(b'F',b'f'*70000))
    assert incoming.feed(out.get_nowait()[5:]) is None
    out.put(record(b'J',b'{"type":"input"}'));out.put(record(b'J',b'{"type":"file_end"}'))
    assert incoming.feed(out.get_nowait()[5:])==(b'J',b'{"type":"input"}')
    results=[]
    while out.qsize():
        item=incoming.feed(out.get_nowait()[5:])
        if item:results.append(item)
    assert results.index((b'F',b'f'*70000))<results.index((b'J',b'{"type":"file_end"}'))
    assert (b'V',b'v'*200000) in results

def test_multiplex_rejects_overlap_and_out_of_order():
    incoming=Incoming(MAX_RECORD,MAX_CONTROL,ProtocolError)
    assert incoming.feed(META.pack(1,b'V',1,5,0)+b'ab') is None
    with pytest.raises(ProtocolError):incoming.feed(META.pack(1,b'V',1,5,3)+b'cd')
    with pytest.raises(ProtocolError):incoming.feed(META.pack(1,b'V',2,5,0)+b'a')

def test_adaptation_recovers_without_changing_dimensions():
    q=AdaptiveQuality()
    for t in range(1,7):fps,factor=q.observe(60,100,2,now=t)
    assert fps<30 and factor==1
    for t in range(7,150):fps,factor=q.observe(60,1,0,now=t)
    assert fps==60 and factor==1
    q.feedback(delay_ms=900,rtt_ms=50)
    assert q.snapshot()['delivery_ms']>0

@pytest.mark.parametrize('size',[(640,360),(1920,1080),(2560,1440)])
def test_single_video_encoder_and_exact_static_restore(size):
    pipeline=ScreenPipeline();tiles=ScreenDecoder();video=VideoDecoder()
    first=Image.new('RGB',size,'white');last=Image.new('RGB',size,'navy')
    kind,packet,stats=pipeline.encode(first,now=1)
    assert kind==b'V' and tiles.decode(packet).tobytes()==first.tobytes()
    kind,packet,stats=pipeline.encode(last,now=2)
    assert kind==b'W' and len(pipeline.contexts)==1
    assert video.decode(packet).size==size
    kind,packet,stats=pipeline.encode(last,now=3)
    assert kind==b'V' and tiles.decode(packet).tobytes()==last.tobytes()

def test_video_dimensions_bounded_before_encoding():
    with pytest.raises(ProtocolError):ScreenPipeline().encode(Image.new('RGB',(2561,1)),mode='vp8')

def test_embedded_motion_uses_video_and_static_returns_to_lossless():
    pipeline=ScreenPipeline();first=Image.new('RGB',(640,360),'white')
    pipeline.encode(first,now=1)
    changed=first.copy();changed.paste('navy',(80,80,240,160))
    kind,packet,_=pipeline.encode(changed,now=2)
    assert kind==b'W' and VideoDecoder().decode(packet).size==changed.size
    kind,packet,_=pipeline.encode(changed,now=3)
    assert kind==b'V' and ScreenDecoder().decode(packet).tobytes()==changed.tobytes()
    assert ScreenPipeline().encode(changed,mode='deflate',now=4)[0]==b'V'

def test_high_latency_route_does_not_hide_additional_video_queue():
    q=AdaptiveQuality()
    for _ in range(30):q.feedback(delay_ms=1200,rtt_ms=700)
    fps,factor=q.observe(30,5,0,now=1)
    assert fps<30 and factor==1
    healthy=AdaptiveQuality()
    for _ in range(30):healthy.feedback(delay_ms=750,rtt_ms=700)
    assert healthy.observe(30,5,0,now=1)==(30,1.)

def test_original_and_stretch_are_separate_from_stream_resolution():
    from novoacesso.app import MainWindow
    from PySide6.QtTest import QTest
    window=MainWindow();window.show()
    try:
        window.canvas.set_frame(Image.new('RGB',(1920,1080),'white'))
        window.display.setCurrentIndex(1);QTest.qWait(30)
        assert not window.viewer.widgetResizable() and window.canvas.width()==1920
        assert window.quality.currentData()==(1920,30)
        window.display.setCurrentIndex(2);QTest.qWait(30)
        assert window.viewer.widgetResizable() and window.canvas.display_mode=='stretch'
        assert window.view_preferences()['display']=='stretch'
    finally:window.close()

def test_real_tls_legacy_session_remains_usable():
    from novoacesso.session import HostService
    from novoacesso.wire import connect_invitation
    from test_session import FakeDesktop,wait_for
    host=HostService(FakeDesktop(),lambda *a:None,lambda *a:True,{})
    channel=None
    try:
        token=host.start('127.0.0.1',bind_address='127.0.0.1')
        channel,invitation=connect_invitation(token)
        channel.control(dict(type='hello',min=1,max=1,secret=invitation['secret']))
        kind,welcome=channel.receive()
        assert welcome['version']==1
        kind,data=channel.receive()
        assert kind==b'V' and ScreenDecoder().decode(data).size==(128,128)
    finally:
        if channel:channel.close()
        host.stop()

def test_real_tls_v2_video_and_feedback():
    from novoacesso.session import HostService,join
    from test_session import FakeDesktop,wait_for
    host=HostService(FakeDesktop(),lambda *a:None,lambda *a:True,{})
    viewer=None;frames=[]
    try:
        token=host.start('127.0.0.1',bind_address='127.0.0.1')
        viewer=join(token,lambda k,d:frames.append(d) if k=='frame' else None,lambda *a:None);viewer.start()
        wait_for(lambda:host.peer)
        assert viewer.channel.version==host.peer.channel.version==2
        viewer.send(dict(type='view',monitor=1,mode='vp8',width=1920,fps=30))
        wait_for(lambda:len(frames)>4)
        wait_for(lambda:host.peer.quality.snapshot()['delivery_ms']>0)
        assert len(host.peer.sent_frames)<=64
    finally:
        if viewer:viewer.close();viewer.wait_for_workers()
        host.stop()

def test_wan_mode_scales_vp8_bitrate_and_hold_without_resetting_encoder():
    pipeline=ScreenPipeline()
    pipeline.configure_network(rtt_ms=160,wan_mode=True)
    first=Image.new('RGB',(1280,720),'white')
    changed=first.copy();changed.paste('navy',(80,80,480,360))
    pipeline.encode(first,now=1.0)
    kind,_,_=pipeline.encode(changed,now=2.0)
    assert kind==b'W' and 900_000<=pipeline.bitrate<=4_500_000
    context=pipeline.video
    pipeline.configure_network(rtt_ms=210,wan_mode=True)
    assert pipeline.video is context
    # Em WAN, pausas curtas (<1.2s) mantêm VP8 e evitam rajadas DEFLATE repetidas.
    assert pipeline.encode(changed,now=2.8)[0]==b'W'
    assert pipeline.encode(changed,now=3.3)[0]==b'V'

def test_high_rtt_transport_fragment_adaptive_and_four_turn_candidates():
    from novoacesso import multiplex
    from novoacesso.ice_policy import create_peer
    assert multiplex.FRAGMENT==8192 and multiplex.FRAGMENT<=multiplex.MAX_FRAGMENT
    q=AdaptiveQuality()
    for t in range(1,5):fps,factor=q.observe(30,5,2,now=t)
    dropped=fps
    assert dropped<30 and factor==1.
    fps,_=q.observe(30,5,0,now=5)
    assert fps==dropped
    fps,factor=q.observe(30,5,0,now=6)
    assert fps==min(30,dropped+4) and factor==1.
    servers=[
        dict(urls=['turn:turn.example.com:3478?transport=udp'],username='u',credential='p'),
        dict(urls=['turn:turn.example.com:3478?transport=tcp'],username='u',credential='p'),
        dict(urls=['turns:turn.example.com:443?transport=tcp'],username='u',credential='p'),
        dict(urls=['turn:turn.example.com:80?transport=tcp'],username='u',credential='p'),
    ]
    pc=create_peer(servers)
    try:assert len(pc._novo_turn_options)==4
    finally:
        import asyncio
        asyncio.run(pc.close())
