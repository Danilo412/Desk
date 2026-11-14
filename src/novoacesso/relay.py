"""Relay autenticado por TLS externo e túnel TLS 1.3 ponta a ponta via MemoryBIO."""
from __future__ import annotations
import base64,hashlib,json,secrets,socket,ssl,struct,time,re
from .wire import ProtocolError

def token_encode(prefix,data):return prefix+base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
def token_decode(prefix,token):
    if not isinstance(token,str) or not token.startswith(prefix) or len(token)>4096:raise ProtocolError('Configuração inválida.')
    try:
        raw=token[len(prefix):];result=json.loads(base64.b64decode(raw+'='*(-len(raw)%4),altchars=b'-_',validate=True))
        if not isinstance(result,dict):raise ValueError()
        return result
    except (ValueError,TypeError) as ex:raise ProtocolError('Configuração inválida.') from ex

def validate_endpoint(value):
    if isinstance(value,dict) and value.get('mode')=='metered':
        key=value.get('api_key')
        if not isinstance(key,str) or not key.startswith('pk_live_') or not 20<=len(key)<=256 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in key):
            raise ProtocolError('Use a chave pública pk_live_ do Metered, com a permissão Send habilitada.')
        result=dict(mode='metered',api_key=key,host='rms.metered.ca',port=443)
        if 'relay_only' in value:
            if type(value['relay_only']) is not bool:raise ProtocolError('Política de relay inválida.')
            result['relay_only']=value['relay_only']
        if 'ice_servers' in value:
            servers=value['ice_servers']
            if not isinstance(servers,list) or not 1<=len(servers)<=16:raise ProtocolError('Configuração TURN inválida.')
            clean=[]
            for server in servers:
                if not isinstance(server,dict):raise ProtocolError('Servidor TURN inválido.')
                urls=server.get('urls');urls=[urls] if isinstance(urls,str) else urls
                if not isinstance(urls,list) or not 1<=len(urls)<=8 or any(not isinstance(url,str) or not re.fullmatch(r'(?:stun|turn|turns):(?:(?:global\.relay|stun\.relay)\.metered\.ca|(?:[a-z0-9-]+\.)*expressturn\.com):(?:80|443|3478|5349)(?:\?transport=(?:udp|tcp))?',url) for url in urls):raise ProtocolError('Endereço TURN não reconhecido para este serviço.')
                item={'urls':urls}
                if any(url.startswith(('turn:','turns:')) for url in urls):
                    for field in ('username','credential'):
                        part=server.get(field)
                        if not isinstance(part,str) or not 1<=len(part)<=1024:raise ProtocolError('Credencial TURN inválida.')
                        item[field]=part
                clean.append(item)
            result['ice_servers']=clean
        return result
    try:
        assert isinstance(value,dict) and isinstance(value['host'],str) and 0<len(value['host'])<=253
        assert not any(c.isspace() for c in value['host'])
        assert type(value['port']) is int and 1<=value['port']<=65535
        assert len(bytes.fromhex(value['fp']))==32 and isinstance(value['access'],str) and 32<=len(value['access'])<=128
    except (KeyError,ValueError,TypeError,AssertionError) as ex:raise ProtocolError('Endereço, porta ou chave do relay inválidos.') from ex
    return dict(host=value['host'],port=value['port'],fp=value['fp'],access=value['access'])

def endpoint_from_token(token):
    token=token.strip()
    if token.startswith('pk_live_'):return validate_endpoint(dict(mode='metered',api_key=token))
    return validate_endpoint(token_decode('NAR1-',token))

def read_exact(sock,length):
    result=bytearray()
    while len(result)<length:
        chunk=sock.recv(length-len(result))
        if not chunk:raise ConnectionError('Relay desconectado.')
        result.extend(chunk)
    return bytes(result)
def write_json(sock,data):
    raw=json.dumps(data,separators=(',',':')).encode()
    if len(raw)>4096:raise ProtocolError('Mensagem do relay muito grande.')
    sock.sendall(struct.pack('>I',len(raw))+raw)
def read_json(sock):
    size=struct.unpack('>I',read_exact(sock,4))[0]
    if not 1<=size<=4096:raise ProtocolError('Mensagem do relay inválida.')
    result=json.loads(read_exact(sock,size))
    if not isinstance(result,dict):raise ProtocolError('Mensagem do relay inválida.')
    return result

def relay_socket(endpoint,room,route,role,waiting=None,wait_timeout=100,registered=None):
    endpoint=validate_endpoint(endpoint)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
    context.minimum_version=ssl.TLSVersion.TLSv1_3
    raw=socket.create_connection((endpoint['host'],endpoint['port']),timeout=10)
    raw.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);raw.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,65536)
    try:
        sock=context.wrap_socket(raw,server_hostname='novoacesso-relay')
        if hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()!=endpoint['fp']:raise ProtocolError('Certificado do relay diferente da configuração.')
        sock.settimeout(wait_timeout)
        if waiting:waiting(sock)
        write_json(sock,dict(role=role,room=room,route=route,access=endpoint['access']))
        result=read_json(sock)
        if role=='host' and result.get('status')=='registered':
            if registered:registered()
            result=read_json(sock)
        if result.get('status')!='paired':raise ProtocolError(result.get('error','O relay recusou a conexão.'))
        sock.settimeout(10);return sock
    except BaseException:
        try:sock.close()
        except UnboundLocalError:raw.close()
        raise

class InnerTLS:
    """Interface de socket para Channel; somente uma thread faz operações SSL."""
    def __init__(self,outer,context,server_side=False):
        self.outer=outer;self.inbio=ssl.MemoryBIO();self.outbio=ssl.MemoryBIO();self.encrypted=b''
        self.inner=context.wrap_bio(self.inbio,self.outbio,server_side=server_side,server_hostname=None if server_side else 'novoacesso-peer')
        deadline=time.monotonic()+15
        while True:
            if time.monotonic()>deadline:raise TimeoutError('Handshake ponta a ponta excedeu o prazo.')
            try:self.inner.do_handshake();self.flush();break
            except ssl.SSLWantReadError:
                self.flush();data=self.outer.recv(65536)
                if not data:raise ConnectionError('Túnel encerrado durante TLS.')
                self.inbio.write(data)
            except ssl.SSLWantWriteError:self.flush()
    def flush(self):
        while self.outbio.pending:self.encrypted+=self.outbio.read()
        while self.encrypted:
            try:sent=self.outer.send(self.encrypted)
            except BlockingIOError as ex:raise ssl.SSLWantWriteError() from ex
            if not sent:raise ConnectionError('Túnel encerrado.')
            self.encrypted=self.encrypted[sent:]
    def send(self,data):
        self.flush();size=self.inner.write(data)
        try:self.flush()
        except (ssl.SSLWantReadError,ssl.SSLWantWriteError):pass
        return size
    def sendall(self,data):
        while data:data=data[self.send(data):]
        self.flush()
    def recv(self,size):
        self.flush()
        while True:
            try:return self.inner.read(size)
            except ssl.SSLWantReadError:
                try:data=self.outer.recv(65536)
                except BlockingIOError as ex:raise ssl.SSLWantReadError() from ex
                if not data:self.inbio.write_eof();return b''
                self.inbio.write(data)
    def pending(self):
        # SSLObject.pending() sees decrypted bytes only. A previous outer recv
        # can leave complete encrypted TLS records in MemoryBIO after the OS
        # socket becomes empty. The pump must drain those without waiting for
        # another network packet (notably the final fragments of an HD frame).
        return self.inner.pending() or self.inbio.pending or self.outer.pending() or int(bool(self.encrypted) or bool(self.outbio.pending))
    def fileno(self):return self.outer.fileno()
    def settimeout(self,value):self.outer.settimeout(value)
    def setblocking(self,value):self.outer.setblocking(value)
    def getpeercert(self,binary_form=False):return self.inner.getpeercert(binary_form)
    def version(self):return self.inner.version()
    def close(self):self.outer.close()
    def shutdown(self,how):self.outer.shutdown(how)

def peer_client_socket(data):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE;context.minimum_version=ssl.TLSVersion.TLSv1_3
    if data.get('relay'):
        route=data['relay']
        if route.get('mode')=='metered':
            from .metered_stream import open_metered_stream
            validate_endpoint(route);outer=open_metered_stream(route,route['room'],route['route'],'viewer')
        else:outer=relay_socket(route,route['room'],route['route'],'viewer')
        try:sock=InnerTLS(outer,context)
        except BaseException:outer.close();raise
    else:
        raw=socket.create_connection((data['host'],data['port']),timeout=12)
        raw.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);raw.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,65536)
        try:sock=context.wrap_socket(raw,server_hostname='novoacesso')
        except BaseException:raw.close();raise
    if not secrets.compare_digest(hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest(),data['fp']):
        sock.close();raise ProtocolError('O certificado do computador remoto não corresponde ao perfil/convite.')
    return sock
