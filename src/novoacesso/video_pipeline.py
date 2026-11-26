"""Texto por deltas sem perda; movimento amplo por um único codificador VP8."""
import struct,time
from fractions import Fraction
import av,numpy as np
from .codec import ScreenEncoder,ScreenDecoder
from .quality import MAX_WIDTH,MAX_HEIGHT,MAX_PIXELS
from .wire import ProtocolError

HEAD=struct.Struct('>IHH')

class ScreenPipeline:
    def __init__(self):
        self.tiles=ScreenEncoder();self.video=None;self.size=None;self.previous=None;self.moving_until=0.;self.seq=0;self.frames=0;self.last_video=False;self.factor=1.;self.bitrate=0;self.quality_changed=0.;self.last_size=None;self.rtt_ms=0.;self.wan_mode=False
    def configure_network(self,rtt_ms=0.,wan_mode=False):
        """Update RTT/route hints without resetting the active VP8 encoder."""
        self.rtt_ms=max(0.,float(rtt_ms or 0.));self.wan_mode=bool(wan_mode)
    @property
    def contexts(self):return self.tiles.contexts or ({'video':self.video} if self.last_video else {})
    def encode(self,image,mode='auto',now=None):
        if not 1<=image.width<=MAX_WIDTH or not 1<=image.height<=MAX_HEIGHT or image.width*image.height>MAX_PIXELS:raise ProtocolError('Dimensões de captura inválidas.')
        now=time.monotonic() if now is None else now
        small=np.asarray(image.resize((80,45),reducing_gap=3.0).convert('RGB'),dtype=np.int16)
        fraction=0. if self.previous is None else float(np.mean(np.max(np.abs(small-self.previous),axis=2)>18))
        self.previous=small
        distant=bool(self.wan_mode or self.rtt_ms>=65.)
        hold=1.2 if distant else .6
        # Um vídeo incorporado pode movimentar apenas uma pequena região da
        # área de trabalho. Esperar 12% deixava esse caso preso em DEFLATE,
        # acumulando megabytes no relay antes de reduzir a carga.
        if fraction>.035:self.moving_until=now+hold
        video=mode=='vp8' or (mode=='auto' and now<self.moving_until)
        self.seq=(self.seq+1)&0xffffffff;self.frames+=1
        if not video:
            if self.last_video:self.tiles=ScreenEncoder()
            self.last_video=False
            packet,stats=self.tiles.encode(image,'deflate',now)
            return b'V',struct.pack('>I',self.seq)+packet[4:],dict(stats,mode='sem perda')
        # Scale VP8 target bitrate for local vs. distant/relayed links without
        # tearing down the encoder mid-stream; text is restored losslessly on stop.
        desired=int(min(4500000,max(900000,image.width*image.height*1.6))) if distant else int(min(10000000,max(2200000,image.width*image.height*3.5)))
        reset=self.video is None or self.size!=image.size
        if reset:
            ctx=av.CodecContext.create('libvpx','w');ctx.width,ctx.height=image.size;ctx.pix_fmt='yuv420p';ctx.time_base=Fraction(1,1000)
            ctx.bit_rate=desired;ctx.thread_count=4;ctx.framerate=Fraction(30,1)
            ctx.options={'deadline':'realtime','cpu-used':'8' if distant else '7','lag-in-frames':'0','auto-alt-ref':'0','crf':'24' if distant else '18','qmin':'6' if distant else '4','qmax':'38' if distant else '28'};ctx.open()
            self.video=ctx;self.size=image.size;self.pts=-1;self.video_origin=now;self.bitrate=desired;self.quality_changed=now
        self.pts=max(self.pts+1,round((now-self.video_origin)*1000))
        frame=av.VideoFrame.from_image(image).reformat(format='yuv420p');frame.pts=self.pts
        packets=self.video.encode(frame)
        if len(packets)!=1:raise ProtocolError('Codificador de movimento não produziu um quadro imediato.')
        self.last_video=True;self.tiles.contexts.clear()
        return b'W',HEAD.pack(self.seq,*image.size)+bytes(packets[0]),dict(deflate=0,vp8=1,tiles=1,width=image.width,height=image.height,mode='vídeo · nitidez preservada')

class VideoDecoder:
    def __init__(self):self.context=None;self.size=None
    def decode(self,payload):
        if len(payload)<=HEAD.size:raise ProtocolError('Quadro de vídeo incompleto.')
        seq,w,h=HEAD.unpack_from(payload)
        if not 1<=w<=MAX_WIDTH or not 1<=h<=MAX_HEIGHT or w*h>MAX_PIXELS:raise ProtocolError('Dimensões de vídeo inválidas.')
        if self.context is None or self.size!=(w,h):self.context=av.CodecContext.create('vp8','r');self.size=(w,h)
        frames=self.context.decode(av.Packet(payload[HEAD.size:]))
        if len(frames)!=1 or (frames[0].width,frames[0].height)!=(w,h):raise ProtocolError('Vídeo recebido fora dos limites.')
        return frames[0].to_image()
