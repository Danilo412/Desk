"""Fluxo WebRTC para Open Relay/Metered, mantendo o TLS próprio dentro dele.

Somente sinalização passa pelo serviço de mensagens. A mídia do aplicativo
segue no RTCDataChannel confiável, com filas limitadas e contrapressão.
"""
from __future__ import annotations
import asyncio,hashlib,socket,threading,time
from .wire import ProtocolError

class MeteredStream:
    def __init__(self,key,room,route,registered=None,peer_factory=None,ice_servers=None,relay_only=False):
        self.key=key;self.room='novoacesso-'+hashlib.sha256((room+':'+route).encode()).hexdigest()
        self.registered=registered;self.peer_factory=peer_factory
        self.ice_servers=ice_servers
        self.relay_only=relay_only
        self.candidate_types=[]
        self.started=time.monotonic();self.timings={}
        self.sock,self.worker=socket.socketpair();self.ready=threading.Event();self.stopped=threading.Event()
        self.failure=None;self.loop=None;self.done=None
        self.route_info='WebRTC: rota ainda não identificada'
        self.audio_channel=None;self.audio_ready=threading.Event();self.datagram_handler=None;self.remote_peer=None
        self.thread=threading.Thread(target=self._run,daemon=True)
    def _run(self):
        try:asyncio.run(self._session())
        except Exception as ex:self.failure=str(ex).replace(self.key,'[chave]')[:240]
        finally:
            self.stopped.set();self.ready.set()
            try:self.worker.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.worker.close()
    async def _session(self):
        from metered_realtime import MeteredPeer,PeerJoined,DataChannelOpened,DataChannel,DCOpen,DCMessage,DCClose,DCError
        self.loop=asyncio.get_running_loop();self.done=asyncio.Event();self.worker.setblocking(False)
        options=dict(api_key=self.key,reconnect=False)
        if self.ice_servers:
            def pc_factory(injected):
                from .ice_policy import create_peer
                return create_peer(self.ice_servers,self.relay_only)
            options['_pc_factory']=pc_factory
        peer=(self.peer_factory or MeteredPeer)(**options)
        channels=[];audio_channels=[];tasks=[];selected=[None];incoming=asyncio.Queue(maxsize=32)
        def bind_audio(raw,remote):
            if remote is not self.remote_peer:raw.close();return
            if self.audio_channel is raw:return
            if self.audio_channel is not None and self.audio_channel is not raw:raw.close();return
            self.audio_channel=raw;audio_channels.append(raw)
            @raw.on('open')
            def audio_opened():self.audio_ready.set()
            @raw.on('close')
            def audio_closed():self.audio_ready.clear()
            @raw.on('message')
            def audio_message(data):
                handler=self.datagram_handler
                if handler and isinstance(data,bytes) and 24<len(data)<=1400:handler(data)
            if raw.readyState=='open':self.audio_ready.set()
        self._bind_audio=bind_audio
        # 256 KiB in flight, below the data-channel's 512 KiB high-water mark.
        # A 128 KiB window caps a 150 ms route around 7 Mbit/s.
        window=asyncio.BoundedSemaphore(16)
        async def outbound(dc):
            try:
                while not self.done.is_set():
                    await window.acquire()
                    chunk=await self.loop.sock_recv(self.worker,16384)
                    if not chunk:break
                    await dc.send(b'D'+chunk)
            except Exception as ex:self.failure=str(ex).replace(self.key,'[chave]')[:180]
            finally:self.done.set()
        async def inbound(dc):
            try:
                while not self.done.is_set():
                    await self.loop.sock_sendall(self.worker,await incoming.get())
                    await dc.send(b'A')
            except Exception:pass
            finally:self.done.set()
        def bind(raw,remote=None):
            if raw.label=='desk-audio-v1':bind_audio(raw,remote);return
            if len(channels)>=4:raw.close();self.failure='Muitos dispositivos nesta sala.';self.done.set();return
            dc=DataChannel(raw,max_buffered_amount=512*1024,max_queued_sends=8);channels.append(dc)
            def opened(*args):
                if selected[0] is dc:return
                if selected[0] is not None:dc.close();return
                try:
                    # Diagnóstico best-effort para aiortc 1.15; não altera ICE.
                    nominated=remote.pc.sctp.transport.transport._connection._nominated.values()
                    types=[(pair.local_candidate.type,pair.remote_candidate.type) for pair in nominated]
                    self.candidate_types=types
                    if types:self.route_info=('WebRTC: relay forçado · TURN nas duas pontas' if self.relay_only else 'WebRTC: relay') if any('relay' in pair for pair in types) else 'WebRTC: conexão direta'
                except (AttributeError,TypeError):pass
                if self.relay_only and (not self.candidate_types or any(pair!=('relay','relay') for pair in self.candidate_types)):
                    self.failure='Não foi comprovada uma rota TURN em ambas as pontas.';self.done.set();dc.close();return
                self.timings['data_channel_seconds']=round(time.monotonic()-self.started,3)
                selected[0]=dc;tasks.extend([asyncio.create_task(outbound(dc)),asyncio.create_task(inbound(dc))]);self.ready.set()
                self.remote_peer=remote
            def message(event):
                if selected[0] is not dc:return
                data=event.data
                if data==b'A':
                    try:window.release()
                    except ValueError:self.failure='Confirmação WebRTC inválida.';self.done.set()
                    return
                if not isinstance(data,bytes) or not data.startswith(b'D') or not 2<=len(data)<=16385:self.failure='Bloco WebRTC inválido.';self.done.set();return
                try:incoming.put_nowait(data[1:])
                except asyncio.QueueFull:self.failure='Recepção WebRTC excedeu a fila permitida.';self.done.set()
            def closed(*args):
                if selected[0] is dc:self.done.set()
            dc.on(DCOpen,opened);dc.on(DCMessage,message);dc.on(DCClose,closed);dc.on(DCError,closed)
            if dc.ready_state=='open':opened()
        @peer.on(PeerJoined)
        def joined(event):
            remote=event.peer;remote.on(DataChannelOpened,lambda event:bind(event.channel,remote))
            if not remote.polite:bind(remote.create_data_channel('novoacesso-tls',ordered=True),remote)
        try:
            await peer.join(self.room)
            self.timings['signaling_seconds']=round(time.monotonic()-self.started,3)
            if self.registered:self.registered()
            if self.stopped.is_set():return
            await self.done.wait()
        finally:
            for task in tasks:task.cancel()
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            for dc in channels:dc.close()
            self.datagram_handler=None;self.audio_ready.clear()
            for raw in audio_channels:raw.close()
            await peer.close()

    def open_audio_channel(self,timeout=3):
        if not self.loop or not self.remote_peer or self.stopped.is_set():return False
        def create():
            if self.audio_channel is None:
                self._bind_audio(self.remote_peer.create_data_channel('desk-audio-v1',ordered=False,maxRetransmits=0),self.remote_peer)
        try:self.loop.call_soon_threadsafe(create)
        except RuntimeError:return False
        return self.audio_ready.wait(timeout)

    def send_datagram(self,payload):
        if not self.audio_ready.is_set() or self.stopped.is_set() or len(payload)>1400:return False
        def send():
            channel=self.audio_channel
            if channel and channel.readyState=='open' and channel.bufferedAmount<8192:channel.send(payload)
        try:self.loop.call_soon_threadsafe(send);return True
        except RuntimeError:return False
    def open(self,timeout=90,waiting=None):
        if waiting:waiting(self)
        self.thread.start();deadline=None if timeout is None else time.monotonic()+timeout
        while not self.ready.wait(.1):
            if self.stopped.is_set() or (deadline is not None and time.monotonic()>deadline):
                self.close();raise TimeoutError('O outro computador não ficou disponível no serviço dentro do prazo.')
        if self.failure or self.stopped.is_set():self.close();raise ConnectionError(self.failure or 'Conexão WebRTC encerrada.')
        self.sock.settimeout(10)
        return self
    def recv(self,size):return self.sock.recv(size)
    def send(self,data):return self.sock.send(data)
    def sendall(self,data):self.sock.sendall(data)
    def pending(self):return 0
    def fileno(self):return self.sock.fileno()
    def settimeout(self,value):self.sock.settimeout(value)
    def setblocking(self,value):self.sock.setblocking(value)
    def shutdown(self,how):
        try:self.sock.shutdown(how)
        except OSError:pass
        self._stop()
    def _stop(self):
        self.stopped.set()
        if self.loop and self.done:
            try:self.loop.call_soon_threadsafe(self.done.set)
            except RuntimeError:pass
    def close(self):self._stop();self.sock.close()

def open_metered_stream(endpoint,room,route,role,registered=None,waiting=None,timeout=90,peer_factory=None):
    return MeteredStream(endpoint['api_key'],room,route,registered,peer_factory,endpoint.get('ice_servers'),endpoint.get('relay_only',False)).open(timeout=timeout,waiting=waiting)
