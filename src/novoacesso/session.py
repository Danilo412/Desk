"""Sessões consentidas: conexão, permissões, arquivos, chat e mídia."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import queue
import secrets
import socket
import tempfile
import threading
import time
from .wire import Channel,ProtocolError,tls_identity,make_invitation,connect_invitation
from .codec import ScreenEncoder,ScreenDecoder
from .adaptive import AdaptiveQuality
from .video_pipeline import ScreenPipeline,VideoDecoder

MAX_FILE=250*1024*1024
CHUNK=64*1024

class Peer:
    def __init__(self,channel,role,event,request,permissions,backend=None,monitors=None):
        self.channel=channel;self.role=role;self.event=event;self.request=request;self.backend=backend
        self.permissions=dict(permissions);self.monitors=monitors or []
        self.closed=threading.Event();self.paused=False;self.monitor=1;self.mode="auto";self.width=1920;self.fps=30
        self.options_lock=threading.Lock();self.decoder=ScreenDecoder();self.transfers={};self.pending={}
        self.quality=AdaptiveQuality();self.video_decoder=VideoDecoder();self.sent_frames={};self.sent_frame_bytes={};self.feedback_lock=threading.Lock();self.pings={}
        self.transfer_lock=threading.RLock();self.audio_queue=queue.Queue(maxsize=24);self.file_offers_pending=0
        self.audio_capture_running=False;self.audio_capture_attempted=False;self.audio_playback_running=False;self.workers=[]
        from .remote_features import RemoteFeatures
        self.remote_capabilities=set();self.features=RemoteFeatures(self);self.recording_audio_sink=None
        self.remote_media=set();self.capabilities_received=threading.Event();self.opus_decoder=None;self.audio_metrics={};self.audio_format=''
        self.audio_decode_lock=threading.Lock()
        from .audio_transport import FastAudio
        self.fast_audio=FastAudio(self)
        from .input_transport import FastInput
        self.fast_input=FastInput(self);self.input_route_lock=threading.RLock();self.input_lock=threading.RLock()
        self.control_state='desktop';self.control_diagnostic={}
        self.receive_metrics={}
        self.input_apply_ms=0.
        self.authorization_check=None
        self.video_queue=queue.Queue(maxsize=2)
        self.file_send_queue=queue.Queue(maxsize=32);self.file_sender_running=False
        from .input_dispatch import InputDispatcher
        # Host input must not hold the receive thread while Windows/the broker
        # responds. Coalesce consecutive moves on both ends, retaining every
        # button, key and release in order. apply_input remains the permission
        # and revocation gate at the moment of actual application.
        self.input_dispatch=InputDispatcher(self._dispatch_input if role=='viewer' else self.apply_input,self.closed,lambda:self.permissions.get('control',False),self.close)

    def spawn(self,fn):
        thread=threading.Thread(target=fn,daemon=True);self.workers.append(thread);thread.start();return thread

    def start(self):
        self.channel.start_io()
        if self.channel.closed.is_set():raise ConnectionError('A conexão foi encerrada antes de iniciar a sessão.')
        if self.role=='viewer':self.spawn(self._decode_video)
        self.spawn(self._receive);self.spawn(self._heartbeat)
        if self.authorization_check:self.spawn(self._authorization_watch)
        if self.role=="host":
            if self.permissions.get('control') and callable(getattr(self.backend,'begin_secure_session',None)):self.backend.begin_secure_session()
            self.spawn(self._capture)
            self.spawn(self._audio_watch)
            if callable(getattr(self.backend,'cursor',None)):self.spawn(self._cursor_updates)
            if callable(getattr(self.backend,'input_desktop_state',None)):self.spawn(self._desktop_watch)
        from .remote_features import CAPABILITIES
        from .audio_codec import CAPABILITY
        from .audio_transport import CAPABILITY as FAST_AUDIO
        from .input_transport import CAPABILITY as FAST_INPUT
        if getattr(self.channel,'version',1)>=2:self.send(dict(type='capabilities',values=sorted(CAPABILITIES|{CAPABILITY,FAST_AUDIO,FAST_INPUT})))
        self.event("connected",dict(role=self.role,permissions=self.permissions,monitors=self.monitors))

    def send(self,data):
        try:self.channel.control(data)
        except (OSError,ConnectionError,ProtocolError) as ex:self.close(str(ex))

    def send_input(self,data):
        if self.role=='viewer' and self.permissions.get('control',False):self.input_dispatch.put(data)

    def _dispatch_input(self,value):
        with self.input_route_lock:
            if not self.fast_input.send(value):self.send(value)

    def report_control_state(self,state,diagnostic=None):
        diagnostic=diagnostic or {}
        if state==self.control_state and diagnostic==self.control_diagnostic:return
        self.control_state=state;self.control_diagnostic=diagnostic
        self.send(dict(type='control_state',state=state,diagnostic=diagnostic))

    def _desktop_watch(self):
        while not self.closed.is_set():
            try:
                state=self.backend.input_desktop_state()
                with self.input_lock:
                    if state!='desktop' and self.control_state=='desktop':self.backend.release()
                    if state!='desktop' or self.control_state!='denied':self.report_control_state(state)
            except Exception:pass
            self.closed.wait(.5)

    def apply_input(self,msg):
        with self.input_lock:
            if self.closed.is_set() or self.role!='host' or not self.permissions.get('control',False):return
            if self.authorization_check and not self.authorization_check():self.close('Acesso por senha revogado localmente.');return
            if self.control_state=='protected':return
            try:
                input_begin=time.monotonic()
                self.backend.input(msg)
                measured=(time.monotonic()-input_begin)*1000
                self.input_apply_ms=.7*self.input_apply_ms+.3*measured if self.input_apply_ms else measured
                if self.control_state=='denied':self.report_control_state('desktop')
            except OSError as error:
                code=getattr(error,'winerror',None)
                if type(code) is not int:code=error.errno
                diagnostic={}
                if type(code) is int and 0<=code<=65535:diagnostic['code']=code
                backend=getattr(error,'input_backend','windows');reason=getattr(error,'input_reason','input_rejected')
                if backend in ('windows','service'):diagnostic['backend']=backend
                if reason in ('input_rejected','capture_required','geometry_mismatch','desktop_changed','service_unavailable'):diagnostic['reason']=reason
                try:self.backend.release()
                except OSError:pass
                self.report_control_state('denied',diagnostic)

    def set_permissions(self,permissions):
        if self.role!="host":return
        with self.input_lock:
            old=self.permissions.copy();self.permissions.update(permissions)
            if old.get('control') and not self.permissions.get('control'):self.input_dispatch.stop()
            if old.get('control') and not self.permissions.get('control') and self.backend:self.backend.release()
            if old.get('control') and not self.permissions.get('control') and callable(getattr(self.backend,'end_secure_session',None)):self.backend.end_secure_session()
            if not old.get('control') and self.permissions.get('control') and callable(getattr(self.backend,'begin_secure_session',None)):self.backend.begin_secure_session()
        if not self.permissions.get("audio") or not old.get("audio"):self.audio_capture_attempted=False
        if old.get('control') and not self.permissions.get('control'):self.features.revoke()
        self.send(dict(type="permissions",values=self.permissions))

    def _authorization_watch(self):
        while not self.closed.wait(.1):
            try:allowed=self.authorization_check()
            except Exception:allowed=False
            if not allowed:self.close('Acesso por senha revogado localmente.');return

    def _heartbeat(self):
        if getattr(self.channel,'version',1)<2 and self.closed.wait(4):return
        while not self.closed.is_set():
            self.features.expire()
            nonce=secrets.token_hex(8)
            with self.feedback_lock:
                self.pings={nonce:time.monotonic()}
            self.send(dict(type="ping",nonce=nonce))
            self.closed.wait(4)

    def _cursor_updates(self):
        last=None
        while not self.closed.wait(.02):
            try:shape=self.backend.cursor()
            except Exception:return
            if shape!=last:
                last=shape;self.send(dict(type='cursor',shape=shape))

    def _audio_watch(self):
        from .audio import capture_loop
        while not self.closed.wait(.1):
            if self.permissions.get('audio',False) and not self.audio_capture_running and not self.audio_capture_attempted:
                self.audio_capture_running=True;self.audio_capture_attempted=True
                self.spawn(lambda:capture_loop(self))

    def _capture(self):
        modern=getattr(self.channel,'version',1)>=2
        encoder=ScreenPipeline() if modern else ScreenEncoder();last_stats=0;sent=0;started=time.monotonic()
        try:
            with self.backend.capture_source() as source:
                while not self.closed.is_set():
                    begin=time.monotonic()
                    with self.options_lock:paused,monitor,width,fps,mode=self.paused,self.monitor,self.width,self.fps,self.mode
                    if paused or self.control_state=='protected':
                        self.closed.wait(.1);continue
                    if modern:
                        import math
                        budget=max(2,min(8,math.ceil(max(50,self.quality.rtt_ms)*fps/1000)+1))
                        with self.feedback_lock:
                            waiting=len(self.sent_frames)>=budget or sum(self.sent_frame_bytes.values())>=192*1024
                        if waiting:
                            self.quality.observe(fps,self.quality.encode_ms,2);self.closed.wait(.005);continue
                    # Não gerar deltas enquanto os quadros anteriores aguardam envio.
                    # Pular antes de codificar preserva a cadeia de deltas e evita atraso acumulado.
                    if getattr(self.channel.outgoing,'video_pending',self.channel.outgoing.qsize)()>=2:
                        if modern:self.quality.observe(fps,self.quality.encode_ms,2)
                        self.closed.wait(.01);continue
                    if hasattr(source,'separate_cursor'):source.separate_cursor=bool(self.permissions.get('control'))
                    capture_begin=time.monotonic()
                    try:image=self.backend.capture(source,monitor,width)
                    except Exception:
                        probe=getattr(self.backend,'input_desktop_state',None)
                        if callable(probe) and probe()=='protected':
                            with self.input_lock:
                                self.backend.release();self.report_control_state('protected')
                            self.closed.wait(.1);continue
                        raise
                    if getattr(source,'unchanged',False) and encoder.frames and not encoder.contexts:
                        self.closed.wait(1/fps);continue
                    backlog=getattr(self.channel.outgoing,'video_pending',self.channel.outgoing.qsize)()
                    encode_begin=time.monotonic()
                    if modern:
                        frame_kind,payload,stats=encoder.encode(image,mode)
                    else:
                        payload,stats=encoder.encode(image,mode);frame_kind=b'V'
                    effective,factor=self.quality.observe(fps,(time.monotonic()-encode_begin)*1000,backlog)
                    if modern:
                        encoder.factor=factor
                        import struct
                        seq=struct.unpack_from('>I',payload)[0]
                        with self.feedback_lock:
                            self.sent_frames[seq]=begin
                            self.sent_frame_bytes[seq]=len(payload)
                            while len(self.sent_frames)>64:
                                previous=next(iter(self.sent_frames));self.sent_frames.pop(previous);self.sent_frame_bytes.pop(previous,None)
                    self.channel.send(frame_kind,payload);sent+=len(payload)
                    if begin-last_stats>=1:
                        last_stats=begin
                        outer=getattr(self.channel.sock,'outer',None)
                        with self.feedback_lock:pending_frames=len(self.sent_frames);pending_kib=sum(self.sent_frame_bytes.values())/1024
                        report=dict(**stats,frames=encoder.frames,seconds=begin-started,bytes=sent,**self.quality.snapshot(),capture_ms=round((encode_begin-capture_begin)*1000,2),input_apply_ms=round(self.input_apply_ms,2),pending_frames=pending_frames,pending_kib=round(pending_kib,1),input_fast=int(self.fast_input.active),control_route='service' if getattr(self.backend,'service_input_route',False) else 'windows',capture=getattr(source,'backend','MSS'),route=getattr(outer,'route_info','TLS direto' if outer is None else 'Relay TCP'))
                        self.event("stats",report)
                        self.channel.control(dict(type="stats",values=report))
                    self.closed.wait(max(0,1/(effective if modern else fps)-(time.monotonic()-begin)))
        except Exception as ex:self.close("Transmissão interrompida: "+str(ex)[:200])

    def _receive(self):
        try:
            while not self.closed.is_set():
                kind,data=self.channel.receive()
                if kind==b"J":self._control(data)
                elif kind in (b"V",b"W"):
                    if self.role!="viewer":raise ProtocolError("Quadro recebido no papel incorreto.")
                    # Decode independently so heavy HD frames do not stall audio.
                    while not self.closed.is_set():
                        try:self.video_queue.put((kind,data),timeout=.05);break
                        except queue.Full:continue
                elif kind==b"F":self._file_chunk(data)
                elif kind==b"A":
                    from .audio import receive_audio
                    with self.audio_decode_lock:receive_audio(self,data)
        except Exception as ex:self.close(str(ex)[:220])

    def _decode_video(self):
        sample_start=time.monotonic();sample_frames=0;sample_bytes=0;sample_decode=0.
        try:
            while not self.closed.is_set():
                try:kind,data=self.video_queue.get(timeout=.1)
                except queue.Empty:continue
                decode_start=time.monotonic()
                image=self.decoder.decode(data) if kind==b'V' else self.video_decoder.decode(data)
                sample_decode+=time.monotonic()-decode_start;sample_frames+=1;sample_bytes+=len(data)
                if self.closed.is_set():return
                self.event('frame',image)
                now=time.monotonic();elapsed=now-sample_start
                if elapsed>=1:
                    self.receive_metrics=dict(received_fps=round(sample_frames/elapsed,1),decode_ms=round(sample_decode*1000/sample_frames,2),received_kbps=round(sample_bytes*8/elapsed/1000,1))
                    self.event('receive_stats',self.receive_metrics)
                    sample_start=now;sample_frames=0;sample_bytes=0;sample_decode=0.
                if self.channel.version>=2:
                    import struct
                    self.send(dict(type='frame_ack',seq=struct.unpack_from('>I',data)[0]))
        except Exception as ex:self.close('Decodificação interrompida: '+str(ex)[:180])

    def _control(self,msg):
        kind=msg["type"]
        if kind=='capabilities':
            self.features.handle(msg)
            from .audio_codec import CAPABILITY
            from .audio_transport import CAPABILITY as FAST_AUDIO
            from .input_transport import CAPABILITY as FAST_INPUT
            self.remote_media=set(msg['values'])&{CAPABILITY,FAST_AUDIO,FAST_INPUT};self.capabilities_received.set();self.fast_input.negotiate();return
        if kind in ('audio_route','audio_route_ready'):self.fast_audio.handle(msg);return
        if kind in ('input_route','input_route_ready'):self.fast_input.handle(msg);return
        if kind=='control_state':
            if self.role=='viewer' and msg.get('state') in ('desktop','protected','denied'):
                value=msg.get('diagnostic');diagnostic={}
                if isinstance(value,dict) and msg['state']=='denied':
                    if type(value.get('code')) is int and 0<=value['code']<=65535:diagnostic['code']=value['code']
                    if value.get('backend') in ('windows','service'):diagnostic['backend']=value['backend']
                    if value.get('reason') in ('input_rejected','capture_required','geometry_mismatch','desktop_changed','service_unavailable'):diagnostic['reason']=value['reason']
                self.control_state=msg['state'];self.control_diagnostic=diagnostic
                self.event('control_state',dict(state=self.control_state,diagnostic=diagnostic))
            return
        if kind in ('advanced_request','advanced_result','whiteboard_state','annotation'):
            self.features.handle(msg);return
        if kind=='cursor':
            if self.role=='viewer' and msg.get('shape') in ('arrow','ibeam','wait','cross','hand','size_all','size_we','size_ns','size_nwse','size_nesw','forbidden','busy'):
                self.event('cursor',dict(shape=msg['shape']))
            return
        if kind=='ping':
            nonce=msg.get('nonce')
            if isinstance(nonce,str) and len(nonce)<=32:self.send(dict(type='pong',nonce=nonce))
            return
        if kind=='pong':
            with self.feedback_lock:start=self.pings.pop(msg.get('nonce'),None)
            if start is not None:self.quality.feedback(rtt_ms=(time.monotonic()-start)*1000)
            return
        if kind=='frame_ack' and self.role=='host':
            seq=msg.get('seq')
            if type(seq) is int:
                with self.feedback_lock:start=self.sent_frames.pop(seq,None);self.sent_frame_bytes.pop(seq,None)
                if start is not None:self.quality.feedback(delay_ms=(time.monotonic()-start)*1000)
            return
        if kind=="bye":self.close("Sessão encerrada pelo outro computador.")
        elif kind=="chat":
            text=msg.get("text")
            if isinstance(text,str) and len(text)<=4000:self.event("chat",{"text":text})
        elif kind=='permanent_profile' and self.role=='viewer':
            from .unattended import parse_profile
            token=msg.get('profile');profile=parse_profile(token)
            if profile['fp']!=hashlib.sha256(self.channel.sock.getpeercert(binary_form=True)).hexdigest():raise ProtocolError('Perfil salvo não pertence ao computador desta sessão.')
            name=msg.get('name','Computador remoto')
            if not isinstance(name,str) or len(name)>80:raise ProtocolError('Nome do computador inválido.')
            self.event('permanent_profile',{'profile':token,'name':name})
        elif kind=="input" and self.role=="host" and self.permissions.get("control",False):
            self.input_dispatch.put(msg)
        elif kind=="permissions" and self.role=="viewer":
            values=msg.get("values",{})
            if not isinstance(values,dict):raise ProtocolError("Permissões inválidas.")
            self.permissions={k:values.get(k) is True for k in ("control","clipboard","audio")}
            if not self.permissions.get('control'):self.features.revoke()
            else:self.fast_input.negotiate()
            self.event("permissions",self.permissions)
        elif kind=="stats" and self.role=="viewer":
            values=msg.get("values",{})
            if isinstance(values,dict) and all(type(values.get(k)) in (int,float) and 0<=values[k]<1e15 for k in ("deflate","vp8","width","height","frames","seconds","bytes")):
                self.event("stats",values)
        elif kind=="clipboard":
            if (self.role=="host" and not self.permissions.get("clipboard",False)) or not self.permissions.get("clipboard",False):return
            text=msg.get("text")
            if isinstance(text,str) and len(text.encode())<=32000:self.event("clipboard",{"text":text})
        elif kind=="view" and self.role=="host":
            monitor,mode,width,fps=msg.get("monitor"),msg.get("mode"),msg.get("width"),msg.get("fps")
            from .quality import WIDTHS,FPS
            if type(monitor) is int and 0<=monitor<len(self.monitors) and mode in ("auto","deflate","vp8") and width in WIDTHS and type(width) is int and fps in FPS and type(fps) is int:
                if monitor!=self.monitor and self.features.whiteboard_allowed:self.features.revoke()
                with self.options_lock:self.monitor,self.mode,self.width,self.fps=monitor,mode,width,fps
        elif kind=="file_offer":
            with self.transfer_lock:
                if self.file_offers_pending:
                    self.send(dict(type="file_accept",id=msg.get("id"),accepted=False));return
                self.file_offers_pending+=1
            def offer():
                try:self._file_offer(msg)
                except Exception as ex:self.close(str(ex))
                finally:
                    with self.transfer_lock:self.file_offers_pending-=1
            self.spawn(offer)
        elif kind=="file_accept":
            with self.transfer_lock:item=self.pending.get(msg.get("id"))
            if item is not None:item["accepted"]=msg.get("accepted") is True;item["event"].set()
        elif kind=="file_end":self._file_end(msg)

    def send_file(self,path):
        def worker():
            transfer=secrets.token_hex(8);size=0;sent=0;last_progress=0
            try:
                size=path.stat().st_size
                if not 0<=size<=MAX_FILE:raise ValueError("O limite de cada arquivo é 250 MB.")
                self.transfer_event(transfer,'send',path.name,size,0,'hashing')
                digest=hashlib.sha256()
                with path.open("rb") as source:
                    for chunk in iter(lambda:source.read(CHUNK),b""):digest.update(chunk)
                item=dict(event=threading.Event(),accepted=False)
                with self.transfer_lock:self.pending[transfer]=item
                self.send(dict(type="file_offer",id=transfer,name=path.name,size=size,sha256=digest.hexdigest()))
                self.transfer_event(transfer,'send',path.name,size,0,'waiting')
                self.event("notice",{"text":"Aguardando aceitação do arquivo "+path.name})
                answered=item['event'].wait(65)
                if self.closed.is_set():raise ConnectionError('A sessão foi encerrada.')
                if not answered or not item['accepted']:
                    self.transfer_event(transfer,'send',path.name,size,0,'declined');return
                with path.open("rb") as source:
                    for chunk in iter(lambda:source.read(CHUNK),b""):
                        if self.closed.is_set():raise ConnectionError('A sessão foi encerrada.')
                        self.channel.send(b"F",transfer.encode()+chunk)
                        sent+=len(chunk)
                        if time.monotonic()-last_progress>=.15 or sent==size:
                            self.transfer_event(transfer,'send',path.name,size,sent,'sending');last_progress=time.monotonic()
                self.send(dict(type="file_end",id=transfer))
                if self.closed.is_set():raise ConnectionError('A sessão foi encerrada.')
                self.transfer_event(transfer,'send',path.name,size,sent,'sent')
                self.event("notice",{"text":"Arquivo enviado: "+path.name})
            except Exception as ex:
                self.transfer_event(transfer,'send',path.name,max(0,min(size,MAX_FILE)),sent,'interrupted' if self.closed.is_set() else 'failed')
                self.event("notice",{"text":"Envio de arquivo: "+str(ex)[:180]})
            finally:
                with self.transfer_lock:self.pending.pop(transfer,None)
        return self.spawn(worker)

    def queue_files(self,paths):
        paths=[Path(path) for path in paths]
        if not paths:return
        with self.transfer_lock:
            if self.closed.is_set():raise ConnectionError('A sessão foi encerrada.')
            if len(paths)>self.file_send_queue.maxsize-self.file_send_queue.qsize():raise ValueError('Aguarde a fila atual. É possível deixar até 32 arquivos ou pastas na fila.')
            for path in paths:self.file_send_queue.put_nowait(path)
            if not self.file_sender_running:
                self.file_sender_running=True;self.spawn(self._send_queued_files)

    def _send_queued_files(self):
        while True:
            with self.transfer_lock:
                if self.closed.is_set():
                    while not self.file_send_queue.empty():self.file_send_queue.get_nowait()
                try:path=self.file_send_queue.get_nowait()
                except queue.Empty:self.file_sender_running=False;return
            worker=self.send_folder(path) if path.is_dir() else self.send_file(path)
            worker.join()

    def send_folder(self,path):
        def worker():
            try:
                from .folders import pack_folder
                with tempfile.TemporaryDirectory(prefix='desk-folder-send-') as directory:
                    archive=Path(directory)/(Path(path).name+'.zip')
                    self.event('notice',dict(text='Preparando a pasta para envio…'))
                    pack_folder(path,archive,self.closed.is_set)
                    if not self.closed.is_set():self.send_file(archive).join()
            except Exception as ex:self.event('notice',dict(text='Envio de pasta: '+str(ex)[:180]))
        return self.spawn(worker)

    def transfer_event(self,id,direction,name,size,done,state):
        self.event('transfer',dict(id=id,direction=direction,name=name,size=size,done=done,state=state))

    def _file_offer(self,msg):
        transfer,name,size,digest=msg.get("id"),msg.get("name"),msg.get("size"),msg.get("sha256")
        if not isinstance(transfer,str) or len(transfer)!=16 or any(c not in "0123456789abcdef" for c in transfer):raise ProtocolError("ID de arquivo inválido.")
        if not isinstance(name,str) or len(name)>255 or type(size) is not int or not 0<=size<=MAX_FILE or not isinstance(digest,str) or len(digest)!=64:raise ProtocolError("Oferta de arquivo inválida.")
        name=Path(name.replace("\\","/")).name
        if not name or name in (".",".."):raise ProtocolError("Nome de arquivo inválido.")
        with self.transfer_lock:
            if len(self.transfers)>=2 or transfer in self.transfers:
                self.send(dict(type="file_accept",id=transfer,accepted=False));return
        self.transfer_event(transfer,'receive',name,size,0,'waiting')
        destination=self.request("save_file",dict(name=name,size=size,_cancelled=self.closed.is_set),60)
        if not destination or self.closed.is_set():
            self.transfer_event(transfer,'receive',name,size,0,'interrupted' if self.closed.is_set() else 'declined')
            self.send(dict(type="file_accept",id=transfer,accepted=False));return
        path=Path(destination)
        temp=tempfile.NamedTemporaryFile(prefix=".novoacesso-",suffix=".part",dir=path.parent,delete=False)
        with self.transfer_lock:self.transfers[transfer]=dict(file=temp,temp=Path(temp.name),destination=path,name=name,size=size,received=0,digest=digest,hash=hashlib.sha256(),last_progress=0)
        self.transfer_event(transfer,'receive',name,size,0,'receiving')
        self.send(dict(type="file_accept",id=transfer,accepted=True))

    def _file_chunk(self,payload):
        if not 16<=len(payload)<=16+CHUNK:raise ProtocolError("Fragmento de arquivo inválido.")
        transfer=payload[:16].decode("ascii");chunk=payload[16:]
        with self.transfer_lock:
            item=self.transfers.get(transfer)
            if item is None or item["received"]+len(chunk)>item["size"]:raise ProtocolError("Transferência não autorizada ou tamanho excedido.")
            item["file"].write(chunk);item["hash"].update(chunk);item["received"]+=len(chunk)
            if time.monotonic()-item['last_progress']>=.15 or item['received']==item['size']:
                self.transfer_event(transfer,'receive',item['name'],item['size'],item['received'],'receiving');item['last_progress']=time.monotonic()

    def _file_end(self,msg):
        with self.transfer_lock:item=self.transfers.pop(msg.get("id"),None)
        if item is None:raise ProtocolError("Transferência desconhecida.")
        try:
            item["file"].flush();os.fsync(item["file"].fileno());item["file"].close()
            if item["received"]!=item["size"] or not secrets.compare_digest(item["hash"].hexdigest(),item["digest"]):raise ProtocolError("O arquivo recebido não passou na conferência de integridade.")
            item["temp"].replace(item["destination"])
            self.transfer_event(msg['id'],'receive',item['destination'].name,item['size'],item['received'],'verified')
            self.event("notice",{"text":"Arquivo recebido e conferido: "+item["destination"].name})
            self.event('file_received',dict(path=str(item['destination']),name=item['destination'].name))
        except Exception:
            self.transfer_event(msg['id'],'receive',item['name'],item['size'],item['received'],'failed');raise
        finally:
            item["file"].close();item["temp"].unlink(missing_ok=True)

    def close(self,reason="Sessão encerrada."):
        if self.closed.is_set():return
        self.closed.set();self.input_dispatch.stop();self.fast_audio.stop();self.fast_input.stop();self.channel.close()
        self.features.revoke();self.recording_audio_sink=None
        if self.backend:
            if callable(getattr(self.backend,'end_secure_session',None)):self.backend.end_secure_session()
            self.backend.release()
        with self.transfer_lock:
            for id,item in self.transfers.items():
                self.transfer_event(id,'receive',item['name'],item['size'],item['received'],'interrupted')
                item["file"].close();item["temp"].unlink(missing_ok=True)
            self.transfers.clear()
            for item in self.pending.values():item["event"].set()
        self.event("disconnected",{"text":reason})

    def wait_for_workers(self,timeout=1):
        deadline=time.monotonic()+timeout
        for thread in [*self.workers,self.input_dispatch.thread,self.channel.io_thread]:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=max(0,deadline-time.monotonic()))

class HostService:
    def __init__(self,backend,event,request,permissions,identity=None,relay=None,gate=None):
        self.backend=backend;self.event=event;self.request=request;self.permissions=dict(permissions)
        self.closed=threading.Event();self.listener=None;self.peer=None;self.used=False;self.invitation=None;self.token=""
        self.identity=identity;self.relay=relay;self.gate=gate or threading.Lock();self.waiting_socket=None
        self.approval_channel=None

    def start(self,host,port=0,bind_address="0.0.0.0"):
        self.context,fp=self.identity.tls_identity() if self.identity else tls_identity()
        if self.relay:
            self.route=dict(self.relay,room=secrets.token_hex(32),route=secrets.token_urlsafe(32))
            self.invitation,self.token=make_invitation(self.relay['host'],self.relay['port'],fp,relay=self.route)
            threading.Thread(target=self._accept,daemon=True).start();return self.token
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        if os.name=="nt":self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        self.listener.bind((bind_address,port));self.listener.listen(2);self.listener.settimeout(1)
        self.invitation,self.token=make_invitation(host,self.listener.getsockname()[1],fp)
        threading.Thread(target=self._accept,daemon=True).start()
        return self.token

    def incoming(self):
        if self.relay:
            from .relay import relay_socket,InnerTLS
            self.event('relay_wait',{'text':'Conectando ao servidor de relay próprio…'})
            params=dict(waiting=lambda s:setattr(self,'waiting_socket',s),registered=lambda:self.event('relay_ready',{'text':'Serviço conectado. Aguardando o outro computador.'}))
            if self.route.get('mode')=='metered':
                from .metered_stream import open_metered_stream
                timeout=max(1,self.invitation['expires']-time.time()) if self.invitation else None
                outer=open_metered_stream(self.route,self.route['room'],self.route['route'],'host',timeout=timeout,**params)
            else:outer=relay_socket(self.route,self.route['room'],self.route['route'],'host',**params)
            try:return Channel(InnerTLS(outer,self.context,True)),('relay',0)
            except BaseException:outer.close();raise
        raw,address=self.listener.accept();raw.settimeout(8)
        raw.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);raw.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,65536)
        try:return Channel(self.context.wrap_socket(raw,server_side=True)),address
        except BaseException:raw.close();raise

    def establish(self,channel,monitors,device_public=None,authorization_check=None):
        if self.closed.is_set() or channel.closed.is_set():raise ConnectionAbortedError('A solicitação já foi encerrada.')
        if not self.gate.acquire(False):raise ProtocolError('Este computador já possui uma sessão ativa.')
        released=False;peer=None
        def event(name,data):
            nonlocal released
            if name=='disconnected' and not released:released=True;self.gate.release()
            self.event(name,data)
        try:
            welcome=dict(type='welcome',version=channel.version,permissions=self.permissions,monitors=monitors)
            if channel.handshake_mode:channel.accept_handshake(welcome)
            else:channel.control(welcome)
            peer=self.peer=Peer(channel,'host',event,self.request,self.permissions,self.backend,monitors)
            peer.authorization_check=authorization_check
            peer.authentication='password' if authorization_check else 'approved'
            self.peer.device_public=device_public;self.peer.start()
        except BaseException:
            if peer:
                peer.close('A conexão foi encerrada antes de iniciar a sessão.');peer.wait_for_workers();self.peer=None
            if not released:released=True;self.gate.release()
            raise

    def _accept(self):
        failures=0
        while not self.closed.is_set() and not self.used and time.time()<self.invitation["expires"]:
            channel=None;raw=None
            try:
                try:channel,address=self.incoming()
                except socket.timeout:continue
                kind,msg=channel.receive()
                if kind!=b"J" or msg.get("type")!="hello" or type(msg.get("min")) is not int or type(msg.get("max")) is not int or not msg["min"]<=1<=msg["max"]:raise ProtocolError("Versão de protocolo incompatível.")
                channel.version=2 if msg['max']>=2 else 1
                secret=msg.get("secret")
                if not isinstance(secret,str) or not secrets.compare_digest(secret,self.invitation["secret"]):raise ProtocolError("Convite não autorizado.")
                if time.time()>=self.invitation["expires"]:raise ProtocolError("Convite expirado.")
                password_access=getattr(self.identity,'password_access',None)
                if password_access and password_access.information()['enabled'] and msg.get('password_supported')==1:
                    # This channel has already completed the pinned encrypted
                    # transport. No screen/input/session exists before verification.
                    self.approval_channel=channel;channel.sock.settimeout(120)
                    nonce=secrets.token_hex(32);channel.control(dict(type='password_required',nonce=nonce))
                    auth_kind,answer=channel.receive()
                    if auth_kind!=b'J' or answer.get('type')!='access_password' or answer.get('nonce')!=nonce:
                        from .wire import AuthorizationError
                        raise AuthorizationError('Autenticação por senha não concluída.')
                    revision=password_access.verify(answer.get('password'));answer.clear()
                    if self.closed.is_set() or not password_access.authorized(revision):raise ProtocolError('Acesso por senha revogado.')
                    channel.sock.settimeout(15)
                    self.establish(channel,self.backend.monitors(),None,authorization_check=lambda:password_access.authorized(revision))
                    self.approval_channel=None;self.used=True
                    if self.listener:self.listener.close()
                    return
                # The same I/O pump owns SSL during approval and during the
                # session. It detects EOF without a second concurrent SSL reader.
                self.approval_channel=channel;channel.start_io(handshake=True)
                public=msg.get('device_public')
                if not isinstance(public,str) or len(public)!=64 or any(c not in '0123456789abcdef' for c in public):public=None
                accepted=self.request("consent",{"address":address[0],"device_public":public,"_cancelled":lambda current=channel:current.closed.is_set() or self.closed.is_set()},60)
                self.approval_channel=None
                if channel.closed.is_set() or self.closed.is_set():raise ConnectionAbortedError('O outro computador encerrou a solicitação antes do aceite.')
                if not accepted or self.closed.is_set():raise ProtocolError("A solicitação não foi aprovada.")
                monitors=self.backend.monitors()
                public=msg.get('device_public')
                if not isinstance(public,str) or len(public)!=64 or any(c not in '0123456789abcdef' for c in public):public=None
                self.establish(channel,monitors,public)
                self.used=True
                if self.listener:self.listener.close()
                return
            except Exception as ex:
                self.approval_channel=None
                from .wire import AuthorizationError
                if channel and isinstance(ex,AuthorizationError):
                    try:channel.control(dict(type='denied',reason='password_not_authorized'))
                    except Exception:pass
                if channel:channel.close()
                elif raw:raw.close()
                failures+=1
                if not self.closed.is_set():
                    if isinstance(ex,ConnectionAbortedError):self.event('incoming_cancelled',{'text':'Solicitação encerrada. O outro computador cancelou ou perdeu a conexão.'})
                    else:self.event("notice",{"text":"Solicitação encerrada: "+str(ex)[:150]})
                if failures>=8:break
        if not self.closed.is_set() and not self.used:self.event("host_expired",{"text":"Convite expirado ou limite de tentativas atingido. Gere um novo convite."})
        if self.listener:
            try:self.listener.close()
            except OSError:pass

    def stop(self):
        self.closed.set()
        if getattr(self,'approval_channel',None):self.approval_channel.close()
        if self.waiting_socket:
            try:
                if isinstance(self.waiting_socket,socket.socket):socket.socket.shutdown(self.waiting_socket,socket.SHUT_RDWR)
                else:self.waiting_socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        if self.listener:
            try:self.listener.close()
            except OSError:pass
        if self.peer:self.peer.close();self.peer.wait_for_workers()

def join(token,event,request,on_channel=None,identity=None,force_relay=False):
    if token.strip().startswith('NAU1-'):
        from .unattended import join_trusted
        if identity is None:raise ProtocolError('Identidade local necessária para acesso permanente.')
        return join_trusted(token,identity,event,request,on_channel,force_relay=True) if force_relay else join_trusted(token,identity,event,request,on_channel)
    channel,data=connect_invitation(token,force_relay=True) if force_relay else connect_invitation(token)
    try:
        if on_channel:on_channel(channel)
        channel.control(dict(type="hello",min=1,max=2,secret=data["secret"],device_public=identity.public if identity else None,password_supported=1))
        channel.sock.settimeout(75)
        kind,msg=channel.receive()
        if kind==b'J' and msg.get('type')=='password_required':
            nonce=msg.get('nonce')
            if not isinstance(nonce,str) or len(nonce)!=64 or any(c not in '0123456789abcdef' for c in nonce):raise ProtocolError('Pedido de senha inválido.')
            channel.sock.settimeout(120)
            answer=request('access_password',{'_cancelled':lambda:channel.closed.is_set()},90)
            if not isinstance(answer,str):raise ConnectionAbortedError('Conexão por senha cancelada.')
            from .password_access import password_bytes
            password_bytes(answer)
            channel.control(dict(type='access_password',nonce=nonce,password=answer));answer=None
            kind,msg=channel.receive()
        if kind==b'J' and msg.get('type')=='denied':
            from .wire import AuthorizationError
            raise AuthorizationError('Senha incorreta, acesso desativado ou limite temporário de tentativas. Confira no computador remoto.')
        if kind!=b"J" or msg.get("type")!="welcome" or msg.get("version") not in (1,2):raise ProtocolError("A sessão não foi aceita.")
        channel.version=msg['version']
        permissions=msg.get("permissions");monitors=msg.get("monitors")
        if not isinstance(permissions,dict) or not isinstance(monitors,list) or not 1<=len(monitors)<=32:raise ProtocolError("Resposta inválida.")
        channel.sock.settimeout(15)
        return Peer(channel,"viewer",event,request,{k:permissions.get(k) is True for k in ("control","clipboard","audio")},monitors=monitors)
    except BaseException:channel.close();raise
