import struct
import zlib
import pytest
from PIL import Image,ImageDraw
from novoacesso.codec import ActivitySelector,ScreenEncoder,ScreenDecoder,HEAD,RECORD,bounded_inflate
from novoacesso.wire import ProtocolError

def test_activity_thresholds_window_and_exit_without_cancellation():
    selector=ActivitySelector(0)
    for i in range(25):selector.observe([(0,0)],(i+1)/24)
    assert selector.rates[(0,0)]>=20
    assert not selector.choose((0,0),1.25)
    assert selector.choose((0,0),1.26)
    selector.observe([],2.1)
    assert selector.choose((0,0),2.1)
    selector.rates[(0,0)]=30
    assert selector.choose((0,0),3.1)  # O teste é estritamente >1 s.
    assert not selector.choose((0,0),3.101)

def test_deflate_exact_odd_dimensions_and_delta_update():
    encoder=ScreenEncoder();decoder=ScreenDecoder()
    image=Image.new("RGB",(129,75),(12,88,199))
    packet,stats=encoder.encode(image,"deflate",now=10)
    assert stats['tiles']==6
    assert decoder.decode(packet).tobytes()==image.tobytes()
    packet,stats=encoder.encode(image,"deflate",now=10.1)
    assert stats['tiles']==0
    assert decoder.decode(packet).tobytes()==image.tobytes()
    image.putpixel((70,20),(255,255,255))
    packet,stats=encoder.encode(image,"deflate",now=10.2)
    assert stats['tiles']==1
    assert decoder.decode(packet).tobytes()==image.tobytes()

def test_vp8_real_roundtrip_and_switch_to_lossless():
    encoder=ScreenEncoder();decoder=ScreenDecoder()
    for t in range(3):
        image=Image.new("RGB",(64,64),(20+t*10,130,80))
        packet,stats=encoder.encode(image,"vp8",now=10+t*.1)
        assert stats['vp8']==1
        decoded=decoder.decode(packet)
        error=sum(abs(a-b) for a,b in zip(decoded.getpixel((30,30)),image.getpixel((30,30))))
        assert error<30
    packet,stats=encoder.encode(image,"deflate",now=10.4)
    assert stats['deflate']==1
    assert decoder.decode(packet).tobytes()==image.tobytes()

def test_automatic_codec_enters_on_frequent_changes():
    encoder=ScreenEncoder();decoder=ScreenDecoder();seen_vp8=False
    for frame in range(60):
        image=Image.new("RGB",(64,64),(frame*3%255,80,100))
        packet,stats=encoder.encode(image,now=frame/30)
        decoder.decode(packet)
        seen_vp8|=stats['vp8']>0
    assert seen_vp8

@pytest.mark.parametrize('payload',[
    HEAD.pack(1,2561,10,0),HEAD.pack(1,10,10,99),
    HEAD.pack(1,10,10,1)+RECORD.pack(64,0,0,0),
    HEAD.pack(1,10,10,1)+RECORD.pack(0,0,9,0),
    HEAD.pack(1,10,10,0)+b'extra',
])
def test_invalid_frames_rejected(payload):
    with pytest.raises(ProtocolError):ScreenDecoder().decode(payload)

def test_deflate_bomb_and_trailing_bytes_rejected():
    with pytest.raises(ProtocolError):bounded_inflate(zlib.compress(b'x'*20000),64*64*3)
    with pytest.raises(ProtocolError):bounded_inflate(zlib.compress(b'x'*4)+b'trailing',4)
