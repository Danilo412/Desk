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
        self.tiles=ScreenEncoder();self.video=None;self.size=None;self.previous=None;self.moving_until=0.;self.seq=0;self.frames=0;self.last_video=False;self.factor=1.;self.bitrate=0;self.quality_changed=0.;self.last_size=None
    @property
    def contexts(self):return self.tiles.contexts or ({'video':self.video} if self.last_video else {})
    def encode(self,image,mode='auto',now=None):
        if not 1<=image.width<=MAX_WIDTH or not 1<=image.height<=MAX_HEIGHT or image.width*image.height>MAX_PIXELS:raise ProtocolError('Dimensões de captura inválidas.')
        now=time.monotonic() if now is None else now
        small=np.asarray(image.resize((80,45)).convert('RGB'),dtype=np.int16)
        fraction=0. if self.previous is None else float(np.mean(np.max(np.abs(small-self.previous),axis=2)>18))
        self.previous=small
        if fraction>.12:self.moving_until=now+.6
        video=mode=='vp8' or (mode=='auto' and now<self.moving_until)
        self.seq=(self.seq+1)&0xffffffff;self.frames+=1
        if not video:
            if self.last_video:self.tiles=ScreenEncoder()
            self.last_video=False;self.video=None
            packet,stats=self.tiles.encode(image,'deflate',now)
            return b'V',struct.pack('>I',self.seq)+packet[4:],dict(stats,mode='sem perda')
        desired=int(min(16000000,max(2000000,image.width*image.height*4))*self.factor)
        reset=self.video is None or self.size!=image.size or (now-self.quality_changed>3 and abs(desired-self.bitrate)>max(1,self.bitrate)*.25)
        if reset:
            ctx=av.CodecContext.create('libvpx','w');ctx.width,ctx.height=image.size;ctx.pix_fmt='yuv420p';ctx.time_base=Fraction(1,1000)
            ctx.bit_rate=desired;ctx.thread_count=2;ctx.options={'deadline':'realtime','cpu-used':'8','lag-in-frames':'0','auto-alt-ref':'0'};ctx.open()
            self.video=ctx;self.size=image.size;self.pts=0;self.bitrate=desired;self.quality_changed=now
        frame=av.VideoFrame.from_image(image).reformat(format='yuv420p');frame.pts=self.pts;self.pts+=17
        packets=self.video.encode(frame)
        if len(packets)!=1:raise ProtocolError('Codificador de movimento não produziu um quadro imediato.')
        self.last_video=True;self.tiles.contexts.clear()
        return b'W',HEAD.pack(self.seq,*image.size)+bytes(packets[0]),dict(deflate=0,vp8=1,tiles=1,width=image.width,height=image.height,mode='vídeo adaptativo')

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
