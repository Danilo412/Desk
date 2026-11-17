"""Synthetic screens and input backend only; never controls the desktop."""
import queue,threading,time
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from novoacesso.codec import ScreenEncoder,ScreenDecoder
from novoacesso.session import Peer


@pytest.mark.parametrize('size',[(1,1),(63,65),(129,127),(1920,1080),(2560,1440)])
def test_sparse_delta_roundtrip_preserves_edges_channels_and_mutable_source(size):
    image=Image.new('RGB',size,(15,30,45));encoder=ScreenEncoder();decoder=ScreenDecoder()
    for index in range(9):
        x=(index*63) % size[0];y=(index*64) % size[1]
        image.putpixel((x,y),(index*23,255-index*13,index*17))
        image.putpixel((size[0]-1,size[1]-1),(10,index*27,250))
        packet,_=encoder.encode(image,'deflate',now=index)
        assert decoder.decode(packet).tobytes()==image.tobytes()
        packet,stats=encoder.encode(image,'deflate',now=index+.1)
        assert stats['tiles']==0 and decoder.decode(packet).tobytes()==image.tobytes()
    image=Image.new('RGB',(65,67),'navy')
    packet,_=encoder.encode(image,'deflate',now=20)
    assert decoder.decode(packet).tobytes()==image.tobytes()


def test_random_delta_roundtrip_and_codec_transitions():
    rng=np.random.default_rng(145);encoder=ScreenEncoder();decoder=ScreenDecoder()
    for index in range(8):
        image=Image.fromarray(rng.integers(0,256,(131,197,3),dtype=np.uint8))
        packet,_=encoder.encode(image,'vp8' if index==3 else 'deflate',now=index*2)
        output=decoder.decode(packet)
        assert output.size==image.size
        if index!=3:assert output.tobytes()==image.tobytes()


def test_unchanged_screen_can_switch_to_video_then_restore_losslessly():
    image=Image.new('RGB',(129,67),'orange');encoder=ScreenEncoder();decoder=ScreenDecoder()
    packet,_=encoder.encode(image,'deflate',now=1);decoder.decode(packet)
    packet,stats=encoder.encode(image,'vp8',now=2);decoder.decode(packet)
    assert stats['vp8']==6
    packet,stats=encoder.encode(image,'deflate',now=3)
    assert stats['deflate']==6 and decoder.decode(packet).tobytes()==image.tobytes()


def test_slow_host_input_keeps_chat_responsive_and_replaces_stale_moves_in_order():
    entered=threading.Event();resume=threading.Event();chat=threading.Event();inputs=[]
    incoming=queue.Queue()
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def control(self,value):pass
        def receive(self):return incoming.get(timeout=2)
        def close(self):self.closed.set()
    def apply(value):
        if not inputs:
            entered.set();assert resume.wait(3)
        inputs.append(value)
    peer=Peer(Channel(),'host',lambda kind,data:chat.set() if kind=='chat' else None,
              lambda *args:None,{'control':True},SimpleNamespace(input=apply,release=lambda:None))
    try:
        peer.spawn(peer._receive)
        incoming.put((b'J',dict(type='input',event='move',x=0,y=0)))
        assert entered.wait(1)
        for i in range(50):incoming.put((b'J',dict(type='input',event='move',x=i/100,y=0)))
        down=dict(type='input',event='button',button='left',down=True,x=.49,y=0)
        up=dict(down,down=False)
        for value in (down,dict(type='input',event='move',x=.9,y=.2),up,
                      dict(type='input',event='key',vk=65,down=True),
                      dict(type='input',event='key',vk=65,down=False)):
            incoming.put((b'J',value))
        incoming.put((b'J',dict(type='chat',text='synthetic test')))
        assert chat.wait(1), 'Windows input blocked the network receive thread'
        resume.set();deadline=time.monotonic()+2
        while len(inputs)<7 and time.monotonic()<deadline:time.sleep(.005)
        assert [v['event'] for v in inputs]==['move','move','button','move','button','key','key']
        assert inputs[1]['x']==.49 and inputs[2]==down and inputs[4]==up
    finally:
        resume.set();peer.close();incoming.put((b'J',dict(type='bye')));peer.wait_for_workers()


def test_queued_input_rechecks_permission_before_application():
    entered=threading.Event();resume=threading.Event();inputs=[]
    def apply(value):entered.set();resume.wait(2);inputs.append(value)
    channel=SimpleNamespace(sock=None,control=lambda value:None,close=lambda:None,version=2,io_thread=None)
    peer=Peer(channel,'host',lambda *args:None,lambda *args:None,{'control':True},SimpleNamespace(input=apply,release=lambda:None))
    try:
        peer._control(dict(type='input',event='move',x=0,y=0));assert entered.wait(1)
        peer._control(dict(type='input',event='key',vk=65,down=True))
        peer.permissions['control']=False;resume.set()
        deadline=time.monotonic()+1
        while not inputs and time.monotonic()<deadline:time.sleep(.005)
        time.sleep(.03)
        assert len(inputs)==1
    finally:resume.set();peer.close();peer.wait_for_workers()
