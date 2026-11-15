"""Negotiated 48 kHz stereo Opus and bounded playback smoothing."""
import struct
from fractions import Fraction
import av
import numpy as np
from .wire import ProtocolError

CAPABILITY='audio_opus48'
RATE=48000
FRAMES=960
HEADER=struct.Struct('>4sI')
MAGIC=b'OP48'

class OpusEncoder:
    def __init__(self):
        self.context=av.CodecContext.create('libopus','w');self.context.sample_rate=RATE
        self.context.layout='stereo';self.context.format='s16';self.context.bit_rate=128000
        self.context.time_base=Fraction(1,RATE)
        self.context.options={'application':'audio','frame_duration':'20','vbr':'constrained'}
        self.context.open();self.sequence=0;self.pts=0
    def encode(self,samples):
        data=np.asarray(samples)
        if data.shape!=(FRAMES,2) or not np.isfinite(data).all():raise ValueError('Bloco estéreo inválido.')
        raw=(np.clip(data,-1,1)*32767).astype('<i2').reshape(1,-1)
        frame=av.AudioFrame.from_ndarray(raw,format='s16',layout='stereo')
        frame.sample_rate=RATE;frame.time_base=Fraction(1,RATE);frame.pts=self.pts;self.pts+=FRAMES
        packets=self.context.encode(frame)
        if len(packets)!=1:raise ProtocolError('O áudio não produziu um bloco imediato.')
        result=HEADER.pack(MAGIC,self.sequence)+bytes(packets[0]);self.sequence=(self.sequence+1)&0xffffffff
        return result

class OpusDecoder:
    def __init__(self):self.context=None;self.next_sequence=None
    def decode(self,payload):
        if not HEADER.size<len(payload)<=HEADER.size+1275:raise ProtocolError('Bloco Opus fora dos limites.')
        magic,seq=HEADER.unpack_from(payload)
        if magic!=MAGIC:raise ProtocolError('Identificador de áudio inválido.')
        # Permission changes can legitimately skip buffered packets. Restart
        # decoding at the next authorized packet rather than ending the session.
        if seq!=self.next_sequence or self.context is None:
            self.context=av.CodecContext.create('opus','r');self.context.sample_rate=RATE;self.context.layout='stereo'
        frames=self.context.decode(av.Packet(payload[HEADER.size:]))
        if len(frames)!=1 or frames[0].samples!=FRAMES or frames[0].sample_rate!=RATE or len(frames[0].layout.channels)!=2:
            raise ProtocolError('Formato de áudio inválido.')
        frame=frames[0];data=frame.to_ndarray()
        if frame.format.is_planar:data=data.T
        else:data=data.reshape(-1,2)
        if not np.isfinite(data).all():raise ProtocolError('Amostras de áudio inválidas.')
        self.next_sequence=(seq+1)&0xffffffff
        return (np.clip(data,-1,1)*32767).astype('<i2').tobytes()

def pcm48(raw,rate):
    """Keep new audio untouched; interpolate the legacy 16 kHz stream."""
    samples=np.frombuffer(raw,dtype='<i2').reshape(-1,2).astype(np.float32)/32768
    if rate==16000:
        positions=np.arange(len(samples)*3,dtype=np.float64)/3
        samples=np.column_stack([np.interp(positions,np.arange(len(samples)),samples[:,i]) for i in range(2)]).astype(np.float32)
    elif rate!=RATE:raise ValueError('Taxa de áudio não suportada.')
    return samples

class AudioPlayout:
    """Route-aware jitter reserve; bounded delay and fades at discontinuities."""
    def __init__(self,reserve_ms=120):
        self.buffer=np.empty((0,2),np.float32);self.target=round(max(120,min(480,reserve_ms))*48);self.started=False;self.rebuffering=True
        self.maximum=max(19200,self.target+11520)
        self.last=np.zeros(2,np.float32);self.discontinuity=False;self.underruns=0;self.dropped=0
    def push(self,samples):
        self.buffer=np.concatenate((self.buffer,samples))
        if len(self.buffer)>self.maximum:
            excess=len(self.buffer)-self.maximum;self.buffer=self.buffer[excess:]
            self.dropped+=excess;self.discontinuity=True
    def take(self):
        if self.rebuffering:
            if len(self.buffer)<self.target:return np.zeros((FRAMES,2),np.float32) if self.started else None
            self.rebuffering=False;self.started=True;self.discontinuity=True
        if len(self.buffer)<FRAMES:
            self.underruns+=1;self.target=min(23040,self.target+5760);self.maximum=max(self.maximum,self.target+11520);self.rebuffering=True;self.discontinuity=True
            block=np.zeros((FRAMES,2),np.float32)
            block[:240]=np.linspace(self.last,np.zeros(2,np.float32),240)
            self.last=np.zeros(2,np.float32);return block
        block=self.buffer[:FRAMES].copy();self.buffer=self.buffer[FRAMES:]
        if self.discontinuity:
            ramp=np.linspace(0,1,240,dtype=np.float32)[:,None]
            block[:240]=self.last*(1-ramp)+block[:240]*ramp;self.discontinuity=False
        self.last=block[-1].copy();return block
