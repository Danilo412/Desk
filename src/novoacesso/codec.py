"""Transmissão própria por blocos 64×64, DEFLATE RGB e VP8 4:2:0.

A métrica e os limiares 20/5 derivam do mapa estático do AnyDesk, mas este
bitstream é independente. Não atribuímos significado às máscaras opacas dele.
"""
from __future__ import annotations
import struct
import time
import zlib
import hashlib
from fractions import Fraction
from PIL import Image
import av
from .wire import ProtocolError

TILE=64
HEAD=struct.Struct(">IHHH")
RECORD=struct.Struct(">HHBI")
from .quality import MAX_PIXELS,MAX_WIDTH,MAX_HEIGHT

def bounded_inflate(payload,expected):
    obj=zlib.decompressobj()
    raw=obj.decompress(payload,expected+1)
    if len(raw)!=expected or not obj.eof or obj.unconsumed_tail or obj.unused_data:
        raise ProtocolError("Bloco comprimido inválido.")
    return raw

class ActivitySelector:
    def __init__(self,now=None):
        now=time.monotonic() if now is None else now
        self.window=now;self.marker=now;self.counts={};self.rates={};self.active=set();self.exits={}

    def observe(self,changed,now):
        for index in changed:self.counts[index]=self.counts.get(index,0)+1
        elapsed=now-self.window
        if elapsed>=1:
            self.rates={i:c/elapsed for i,c in self.counts.items()}
            self.counts.clear();self.window=now

    def choose(self,index,now,mode="auto"):
        if mode=="deflate":return False
        if mode=="vp8":return True
        if now-self.marker<=1.25:return index in self.active
        rate=self.rates.get(index,0)
        if index not in self.active and rate>=20:self.active.add(index)
        if index in self.active and rate<5 and index not in self.exits:self.exits[index]=now
        # Mantém o comportamento observado: uma alta posterior não cancela o timestamp.
        if index in self.exits and now-self.exits[index]>1:
            self.active.discard(index);del self.exits[index]
        return index in self.active

class ScreenEncoder:
    def __init__(self):
        self.size=None;self.last={};self.selector=ActivitySelector();self.contexts={};self.seq=0
        self.total_deflate=0;self.total_vp8=0;self.frames=0;self.last_refresh=time.monotonic()

    def _vp8(self,index,tile):
        if index not in self.contexts:
            ctx=av.CodecContext.create("libvpx","w")
            ctx.width=ctx.height=TILE;ctx.pix_fmt="yuv420p";ctx.time_base=Fraction(1,1000)
            ctx.bit_rate=160000;ctx.thread_count=1
            ctx.options={"deadline":"realtime","cpu-used":"8","lag-in-frames":"0","auto-alt-ref":"0"}
            ctx.open();self.contexts[index]=[ctx,0]
        ctx,pts=self.contexts[index]
        frame=av.VideoFrame.from_image(tile).reformat(format="yuv420p")
        frame.pts=pts;self.contexts[index][1]+=40
        packets=ctx.encode(frame)
        if len(packets)!=1:raise ProtocolError("O codificador VP8 não produziu um quadro imediato.")
        return bytes(packets[0])

    def encode(self,image,mode="auto",now=None):
        now=time.monotonic() if now is None else now
        image=image.convert("RGB")
        if image.width>MAX_WIDTH or image.height>MAX_HEIGHT or image.width*image.height>MAX_PIXELS:raise ProtocolError("Resolução excedida.")
        if image.size!=self.size:
            self.size=image.size;self.last.clear();self.contexts.clear();self.selector=ActivitySelector(now)
        tiles={};changed=set()
        # Comparação de 16×16, agrupada em blocos 64×64; um incremento por quadro.
        for y in range(0,image.height,TILE):
            for x in range(0,image.width,TILE):
                index=(x,y);tile=image.crop((x,y,x+TILE,y+TILE))
                values=hashlib.blake2b(tile.tobytes(),digest_size=8).digest()
                if self.last.get(index)!=values:changed.add(index)
                tiles[index]=(tile,values)
        self.selector.observe(changed,now)
        # Transporte confiável: blocos estáticos já recebidos não precisam ser
        # retransmitidos periodicamente. Trocas VP8/sem perda ainda são enviadas.
        refresh=False
        records=[];deflates=vp8s=0
        for index,(tile,values) in tiles.items():
            use_vp8=self.selector.choose(index,now,mode)
            codec_changed=use_vp8!=(index in self.contexts)
            if index not in changed and not codec_changed and not refresh:continue
            self.last[index]=values
            if use_vp8:
                payload=self._vp8(index,tile);kind=1;vp8s+=1
            else:
                self.contexts.pop(index,None)
                payload=zlib.compress(tile.tobytes(),3);kind=0;deflates+=1
            records.append(RECORD.pack(*index,kind,len(payload))+payload)
        self.seq=(self.seq+1)&0xffffffff;self.frames+=1
        self.total_deflate+=deflates;self.total_vp8+=vp8s
        return HEAD.pack(self.seq,*image.size,len(records))+b"".join(records),dict(deflate=deflates,vp8=vp8s,tiles=len(records),width=image.width,height=image.height)

class ScreenDecoder:
    def __init__(self):self.image=None;self.contexts={};self.last_sequence=None
    def decode(self,payload):
        if len(payload)<HEAD.size:raise ProtocolError("Quadro incompleto.")
        seq,w,h,count=HEAD.unpack_from(payload)
        if not 1<=w<=MAX_WIDTH or not 1<=h<=MAX_HEIGHT or w*h>MAX_PIXELS or count>((w+63)//64)*((h+63)//64):
            raise ProtocolError("Dimensões do quadro inválidas.")
        if self.image is None or self.image.size!=(w,h):
            self.image=Image.new("RGB",(w,h));self.contexts.clear()
        offset=HEAD.size;seen=set()
        for _ in range(count):
            if offset+RECORD.size>len(payload):raise ProtocolError("Bloco incompleto.")
            x,y,kind,length=RECORD.unpack_from(payload,offset);offset+=RECORD.size
            index=(x,y)
            if x>=w or y>=h or x%64 or y%64 or index in seen or length>65536 or offset+length>len(payload):
                raise ProtocolError("Bloco fora dos limites.")
            seen.add(index);data=payload[offset:offset+length];offset+=length
            if kind==0:
                tile=Image.frombytes("RGB",(64,64),bounded_inflate(data,64*64*3))
                self.contexts.pop(index,None)
            elif kind==1:
                ctx=self.contexts.setdefault(index,av.CodecContext.create("vp8","r"))
                frames=ctx.decode(av.Packet(data))
                if len(frames)!=1 or frames[0].width!=64 or frames[0].height!=64:raise ProtocolError("Quadro VP8 inválido.")
                tile=frames[0].to_image()
            else:raise ProtocolError("Codec não reconhecido.")
            self.image.paste(tile,(x,y))
        if offset!=len(payload):raise ProtocolError("Bytes excedentes no quadro.")
        self.last_sequence=seq
        return self.image.copy()
