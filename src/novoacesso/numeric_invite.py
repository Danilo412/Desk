"""Online lookup for fixed Desk addresses and legacy temporary invitations."""
from __future__ import annotations
import asyncio,base64,hashlib,secrets,threading,time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .wire import ProtocolError,parse_invitation
from .device_address import normalize_address,format_address,offer_bytes,verify_offer

def normalize_code(value):
    return normalize_address(value)

def code_material(value):
    code=normalize_code(value)
    material=hashlib.scrypt(code.encode(),salt=b'NovoAcesso numeric invitation v1',n=16384,r=8,p=1,maxmem=64*1024*1024,dklen=32)
    return 'novoacesso-code-'+hashlib.sha256(material+b'room').hexdigest(),hashlib.sha256(material+b'key').digest()

def client_for(key,factory=None):
    from metered_realtime import SignallingClient
    return (factory or SignallingClient)(api_key=key,reconnect=False)

def signalling_error(error):
    code=getattr(error,'code',None);close=getattr(error,'close_code',None)
    if close==4010:return 'O serviço atingiu o limite de conexões simultâneas. Aguarde a liberação de uma conexão e tente novamente.'
    if code=='over_message_quota':return 'A franquia de mensagens do serviço de conexão foi atingida.'
    if close==4011:return 'Muitas solicitações ao serviço de conexão. Aguarde alguns segundos antes de tentar novamente.'
    if close in (4001,4003) or code in ('channel_not_authorized','invalid_token','token_expired'):
        return 'A configuração de internet não autoriza esta rede Desk. Confira se os computadores usam a mesma configuração de conexão.'
    return 'Não foi possível acessar o serviço de localização. Confira a internet e a configuração de conexão.'

class RequestBudget:
    """Bound request traffic in a short window, rather than for the host lifetime."""
    def __init__(self,capacity=20,seconds=10,clock=time.monotonic):
        self.capacity=capacity;self.seconds=seconds;self.clock=clock;self.served={}
    def allow(self,peer):
        now=self.clock();self.served={p:t for p,t in self.served.items() if now-t<self.seconds}
        if peer in self.served or len(self.served)>=self.capacity:return False
        self.served[peer]=now;return True

class NumericInvite:
    def __init__(self,token,key,event,client_factory=None,identity=None):
        invitation=parse_invitation(token)
        self.token=token;self.key=key;self.event=event;self.factory=client_factory
        self.identity=identity
        if identity is not None and invitation['fp']!=identity.certificate_fingerprint:raise ProtocolError('O convite não pertence à identidade deste endereço.')
        self.expires=invitation['expires'];self.code=identity.desk_address if identity is not None else f'{secrets.randbelow(10**12):012d}'
        self.id=secrets.token_hex(12);self.stopped=threading.Event();self.loop=None;self.done=None
        self.thread=threading.Thread(target=self._run,daemon=True)
    def start(self):self.thread.start();return self
    def stop(self):
        self.stopped.set()
        if self.loop and self.done:
            try:self.loop.call_soon_threadsafe(self.done.set)
            except RuntimeError:pass
    def _run(self):
        try:asyncio.run(self._serve())
        except Exception as error:
            if not self.stopped.is_set():self.event('numeric_error',{'id':self.id,'text':signalling_error(error),'retry_ms':60000 if getattr(error,'close_code',None)==4010 else 15000})
    async def _serve(self):
        from metered_realtime import Direct
        room,key=code_material(self.code);client=client_for(self.key,self.factory)
        self.loop=asyncio.get_running_loop();self.done=asyncio.Event();served=RequestBudget()
        @client.on(Direct)
        async def request(event):
            data=event.data
            if self.stopped.is_set() or time.time()>=self.expires or not isinstance(data,dict) or data.get('kind')!='numeric_request':return
            nonce=data.get('nonce')
            if not isinstance(nonce,str) or len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce):return
            if not served.allow(event.sender_peer_id):return
            iv=secrets.token_bytes(12)
            sealed=iv+AESGCM(key).encrypt(iv,self.token.encode(),(room+nonce).encode())
            offer=dict(kind='numeric_offer',nonce=nonce,sealed=base64.urlsafe_b64encode(sealed).decode())
            if self.identity is not None:
                public=self.identity.public
                offer.update(address_version=1,public=public,signature=self.identity.signing_key.sign(offer_bytes(self.code,self.token,nonce,public)).hex())
            await client.send(event.sender_peer_id,offer)
        try:
            await client.connect();await client.subscribe(room)
            if self.stopped.is_set():return
            self.event('numeric_ready',{'id':self.id,'code':format_address(self.code),'expires':self.expires,'fixed':self.identity is not None})
            try:await asyncio.wait_for(self.done.wait(),max(.1,self.expires-time.time()))
            except asyncio.TimeoutError:self.event('numeric_expired',{'id':self.id})
        finally:await client.close()

def resolve_code(code,key,timeout=20,cancelled=None,client_factory=None):
    return asyncio.run(_resolve(code,key,timeout,cancelled,client_factory))['token']

def resolve_address(code,key,timeout=20,cancelled=None,client_factory=None,expected_public=None):
    return asyncio.run(_resolve(code,key,timeout,cancelled,client_factory,True,expected_public))

async def _resolve(code,api_key,timeout,cancelled,factory,require_signed=False,expected_public=None):
    from metered_realtime import Direct,Presence
    room,key=code_material(code);client=client_for(api_key,factory)
    future=asyncio.get_running_loop().create_future();nonce=secrets.token_hex(16);asked=set();rejected_identity=False
    @client.on(Presence)
    async def presence(event):
        if event.channel!=room:return
        for peer in event.joined:
            if len(asked)>=8:break
            if peer.peer_id in asked:continue
            asked.add(peer.peer_id)
            await client.send(peer.peer_id,dict(kind='numeric_request',nonce=nonce))
    @client.on(Direct)
    def offer(event):
        nonlocal rejected_identity
        data=event.data
        if future.done() or event.sender_peer_id not in asked or not isinstance(data,dict) or data.get('kind')!='numeric_offer' or data.get('nonce')!=nonce:return
        sealed=data.get('sealed')
        if not isinstance(sealed,str) or not 32<=len(sealed)<=8192:return
        try:
            raw=base64.b64decode(sealed,altchars=b'-_',validate=True)
            token=AESGCM(key).decrypt(raw[:12],raw[12:],(room+nonce).encode()).decode()
            parse_invitation(token)
            public=None
            if require_signed or data.get('address_version') is not None:
                if data.get('address_version')!=1:raise ProtocolError('Atualize o Desk nos dois computadores para usar o endereço fixo.')
                public=verify_offer(code,token,nonce,data.get('public'),data.get('signature'),expected_public)
        except Exception:
            if require_signed:rejected_identity=True
            return
        future.set_result(dict(token=token,public=public,code=normalize_code(code)))
    stage='connect'
    try:
        async with asyncio.timeout(timeout):
            await client.connect();stage='subscribe';await client.subscribe(room);stage='lookup'
            while not future.done():
                if cancelled and cancelled():raise ConnectionError('Conexão cancelada.')
                await asyncio.wait([future],timeout=.1)
            return future.result()
    except TimeoutError as ex:
        if stage!='lookup':raise ProtocolError(signalling_error(ex)) from ex
        if rejected_identity:raise ProtocolError('A resposta deste endereço não pôde ser verificada. Atualize o Desk nos dois computadores e confira a identidade do dispositivo.') from ex
        if not require_signed:raise ProtocolError('Código não encontrado ou expirado.') from ex
        raise ProtocolError('Dispositivo indisponível. Confira o endereço e mantenha o Desk aberto no outro computador.') from ex
    except ProtocolError:raise
    except Exception as error:
        permanent=getattr(error,'close_code',None) in (4001,4003,4010) or getattr(error,'code',None) in ('channel_not_authorized','invalid_token','token_expired','over_message_quota')
        raise (ProtocolError if permanent else ConnectionError)(signalling_error(error)) from error
    finally:await client.close()
