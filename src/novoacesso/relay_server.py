"""Servidor próprio de relay. Não inicia serviços nem altera firewall."""
from __future__ import annotations
import argparse,collections,json,secrets,select,socket,ssl,threading,time
from pathlib import Path
from .identity import IdentityStore
from .relay import read_json,write_json,token_encode

class RelayServer:
    def __init__(self,store,max_connections=128,max_sessions=64,monthly_byte_limit=None):
        self.store=store;self.context,self.fp=store.tls_identity();self.closed=threading.Event();self.lock=threading.RLock()
        self.slots={};self.active=set();self.capacity=threading.BoundedSemaphore(max_connections);self.session_capacity=threading.BoundedSemaphore(max_sessions);self.listener=None
        self.budget=None
        if monthly_byte_limit:
            from .usage import MonthlyBudget
            self.budget=MonthlyBudget(store.root/'usage.json',monthly_byte_limit)
        settings=store.settings();self.access=settings.get('relay_access')
        if not self.access:self.access=secrets.token_urlsafe(32);store.configure(relay_access=self.access)
    def start(self,bind='0.0.0.0',port=4433,advertise=None,advertise_port=None):
        self.listener=socket.socket();self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.listener.bind((bind,port));self.listener.listen(32);self.listener.settimeout(.5)
        if advertise_port is not None and (type(advertise_port) is not int or not 1<=advertise_port<=65535):raise ValueError('Porta pública inválida.')
        self.endpoint=dict(host=advertise or bind,port=advertise_port or self.listener.getsockname()[1],fp=self.fp,access=self.access)
        self.thread=threading.Thread(target=self._listen,daemon=True);self.thread.start()
        return token_encode('NAR1-',self.endpoint)
    def _listen(self):
        while not self.closed.is_set():
            try:raw,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:break
            if not self.capacity.acquire(False):raw.close();continue
            threading.Thread(target=self._handle,args=(raw,),daemon=True).start()
    def _handle(self,raw):
        sock=None;slot=None;transferred=False
        try:
            raw.settimeout(8);sock=self.context.wrap_socket(raw,server_side=True)
            with self.lock:self.active.add(sock)
            msg=read_json(sock);role=msg.get('role');room=msg.get('room');route=msg.get('route');access=msg.get('access')
            if not isinstance(access,str) or not secrets.compare_digest(access,self.access):raise ValueError('Chave de acesso do relay inválida.')
            if role not in ('host','viewer') or not isinstance(room,str) or len(room)!=64 or any(c not in '0123456789abcdef' for c in room) or not isinstance(route,str) or not 32<=len(route)<=128:raise ValueError('Registro inválido.')
            if role=='viewer':
                with self.lock:
                    slot=self.slots.get(room)
                    if slot is None or slot['viewer'] is not None or not secrets.compare_digest(route,slot['route']):raise ValueError('Computador indisponível no relay.')
                    slot['viewer']=sock;slot['ready'].set();transferred=True
                return
            slot=dict(host=sock,viewer=None,route=route,ready=threading.Event())
            with self.lock:
                if room in self.slots:raise ValueError('Identificador já está conectado.')
                self.slots[room]=slot
            write_json(sock,dict(status='registered'))
            deadline=time.monotonic()+80
            while not self.closed.is_set() and time.monotonic()<deadline and not slot['ready'].wait(.2):
                readable,_,_=select.select([sock],[],[],0)
                if readable:
                    if not sock.recv(1):raise ConnectionError('Anfitrião desconectou.')
                    raise ValueError('Dados inesperados antes do pareamento.')
            with self.lock:
                if self.slots.get(room) is slot:self.slots.pop(room,None)
            viewer=slot['viewer']
            if viewer is None:raise TimeoutError('Aguardando o outro computador.')
            if not self.session_capacity.acquire(False):raise ValueError('Limite de sessões simultâneas do relay atingido.')
            try:
                write_json(sock,dict(status='paired'));write_json(viewer,dict(status='paired'))
                self._bridge(sock,viewer)
            finally:self.session_capacity.release()
        except Exception as ex:
            if sock:
                try:write_json(sock,dict(error=str(ex)[:120]))
                except OSError:pass
        finally:
            if slot is not None and not transferred:
                with self.lock:
                    for key,item in list(self.slots.items()):
                        if item is slot:self.slots.pop(key,None)
                if slot.get('viewer'):
                    with self.lock:self.active.discard(slot['viewer'])
                    slot['viewer'].close()
            if not transferred:
                with self.lock:self.active.discard(sock)
                (sock or raw).close()
            self.capacity.release()
    def _bridge(self,left,right):
        sockets=[left,right];buffers={left:bytearray(),right:bytearray()};pending={left:b'',right:b''};other={left:right,right:left}
        for sock in sockets:sock.setblocking(False)
        last=time.monotonic()
        while not self.closed.is_set() and time.monotonic()-last<120:
            for sock in sockets:
                if not pending[sock] and buffers[sock]:pending[sock]=bytes(buffers[sock]);buffers[sock].clear()
            reads=[s for s in sockets if len(buffers[other[s]])+len(pending[other[s]])<512*1024]
            writes=[s for s in sockets if pending[s]]
            ready_read,ready_write,_=select.select(reads,writes,[],.05)
            for sock in ready_write:
                try:
                    sent=sock.send(pending[sock]);pending[sock]=pending[sock][sent:];last=time.monotonic()
                except (ssl.SSLWantReadError,ssl.SSLWantWriteError):pass
            for sock in reads:
                if sock in ready_read or sock.pending():
                    try:
                        data=sock.recv(65536)
                        if not data:return
                        if self.budget and not self.budget.allow(len(data)+1024):raise RuntimeError('Limite mensal de tráfego do relay atingido.')
                        buffers[other[sock]].extend(data);last=time.monotonic()
                    except (ssl.SSLWantReadError,ssl.SSLWantWriteError):pass
    def stop(self):
        self.closed.set()
        if self.listener:self.listener.close()
        # Os donos das conexões encerram os sockets no máximo no próximo ciclo.
        with self.lock:
            for slot in self.slots.values():slot['ready'].set()

def main():
    parser=argparse.ArgumentParser(description='Novo Acesso Relay próprio — TLS externo e túnel ponta a ponta')
    parser.add_argument('--listen',default='0.0.0.0');parser.add_argument('--port',type=int,default=4433)
    parser.add_argument('--advertise',help='IP ou DNS público alcançável pelos clientes')
    parser.add_argument('--state',default=str(Path.home()/'.novoacesso-relay'))
    args=parser.parse_args()
    if not args.advertise:args.advertise=input('IP ou DNS público deste servidor: ').strip()
    if not args.advertise or len(args.advertise)>253 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in args.advertise):parser.error('Informe somente o IP ou DNS público, sem URL ou porta.')
    store=IdentityStore(args.state);server=RelayServer(store)
    token=server.start(args.listen,args.port,args.advertise)
    output=store.root/'relay-config.txt';output.write_text(token,encoding='utf-8');output.chmod(0o600)
    print(f'Relay próprio ativo em {args.listen}:{server.endpoint["port"]}. Configuração privada: {output}',flush=True)
    print('Distribua a configuração apenas aos seus clientes. Ctrl+C encerra o servidor.',flush=True)
    try:
        while not server.closed.wait(1):pass
    except KeyboardInterrupt:server.stop()
    return 0

if __name__=='__main__':raise SystemExit(main())
