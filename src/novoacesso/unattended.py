"""Acesso permanente somente por chave de um dispositivo autorizado localmente."""
from __future__ import annotations
import secrets,socket,threading,time
from pathlib import Path
from .session import HostService,Peer
from .wire import Channel,ProtocolError
from .relay import token_encode,token_decode,peer_client_socket,validate_endpoint
from .identity import challenge_bytes,verify_proof

def parse_profile(token):
    data=token_decode('NAU1-',token.strip())
    try:
        assert data['v']==1 and isinstance(data['host'],str) and 0<len(data['host'])<=253
        assert type(data['port']) is int and 1<=data['port']<=65535
        assert len(bytes.fromhex(data['fp']))==32
        if data.get('relay'):
            validate_endpoint(data['relay']);assert len(data['relay']['room'])==64 and 32<=len(data['relay']['route'])<=128
    except (KeyError,ValueError,TypeError,AssertionError) as ex:raise ProtocolError('Perfil permanente inválido.') from ex
    return data

class TrustedHost(HostService):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        original=self.request
        def request(kind,data,timeout):
            if kind=='save_file' and self.identity.settings().get('unattended_files',False):
                folder=Path.home()/'Downloads'/'NovoAcesso';folder.mkdir(parents=True,exist_ok=True)
                name=''.join('_' if c in '<>:"/\\|?*' or ord(c)<32 else c for c in data['name']).strip(' .')[:150] or 'arquivo'
                return str(folder/(secrets.token_hex(8)+'-'+name))
            return original(kind,data,timeout)
        self.request=request
    def start(self,host,port=45737,bind_address='0.0.0.0'):
        if not self.identity:raise ValueError('Identidade persistente necessária.')
        self.context,fp=self.identity.tls_identity()
        if self.relay:
            self.route=dict(self.relay,room=self.identity.device_id,route=self.identity.data['route'])
            self.profile=dict(v=1,host=self.relay['host'],port=self.relay['port'],fp=fp,relay=self.route)
        else:
            self.listener=socket.socket();
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            self.listener.bind((bind_address,port));self.listener.listen(2);self.listener.settimeout(1)
            self.profile=dict(v=1,host=host,port=self.listener.getsockname()[1],fp=fp)
        self.token=token_encode('NAU1-',self.profile)
        threading.Thread(target=self._accept_trusted,daemon=True).start()
        return self.token
    def _accept_trusted(self):
        failures=[]
        while not self.closed.is_set():
            channel=None
            try:
                try:channel,address=self.incoming()
                except socket.timeout:continue
                if self.closed.is_set():channel.close();break
                now=time.monotonic();failures=[t for t in failures if now-t<60]
                if len(failures)>=8:raise ProtocolError('Limite temporário de tentativas atingido.')
                if not self.identity.settings().get('unattended',False):raise ProtocolError('Acesso permanente desativado localmente.')
                kind,msg=channel.receive()
                public=msg.get('public') if kind==b'J' else None
                if msg.get('type')!='trusted_hello' or not isinstance(public,str) or not self.identity.trusted(public):raise ProtocolError('Dispositivo não autorizado.')
                channel.version=2 if msg.get('max')==2 else 1
                nonce=secrets.token_hex(32)
                channel.control(dict(type='challenge',nonce=nonce))
                kind,proof=channel.receive()
                if kind!=b'J' or proof.get('type')!='proof' or not verify_proof(public,proof.get('signature'),nonce,self.profile['fp']):raise ProtocolError('Assinatura do dispositivo inválida.')
                if self.closed.is_set() or not self.identity.trusted(public) or not self.identity.settings().get('unattended',False):raise ProtocolError('Autorização revogada.')
                self.establish(channel,self.backend.monitors(),public)
                self.event('notice',{'text':'Acesso permanente por dispositivo previamente autorizado.'})
                while not self.closed.is_set() and not self.peer.closed.wait(.25):
                    if not self.identity.trusted(public) or not self.identity.settings().get('unattended',False):self.peer.close('Autorização revogada localmente.')
                self.peer.wait_for_workers()
            except Exception as ex:
                if channel and isinstance(ex,ProtocolError):
                    try:channel.control(dict(type='denied',reason='not_authorized'))
                    except Exception:pass
                if channel:channel.close()
                if channel:failures.append(time.monotonic())
                if not self.closed.is_set():self.event('notice',{'text':'Acesso permanente: '+str(ex)[:140]})
                self.closed.wait(.25 if channel else 2)
        if self.listener:self.listener.close()

def join_trusted(token,identity,event,request,on_channel=None,force_relay=False):
    profile=parse_profile(token);channel=Channel(peer_client_socket(profile,force_relay=True) if force_relay else peer_client_socket(profile))
    try:
        if on_channel:on_channel(channel)
        channel.control(dict(type='trusted_hello',public=identity.public,max=2))
        kind,msg=channel.receive()
        if kind==b'J' and msg.get('type')=='denied':
            from .wire import AuthorizationError
            raise AuthorizationError('Dispositivo não autorizado ou acesso permanente desativado no computador remoto.')
        if kind!=b'J' or msg.get('type')!='challenge' or not isinstance(msg.get('nonce'),str) or len(msg['nonce'])!=64:raise ProtocolError('Desafio de autenticação inválido.')
        signature=identity.signing_key.sign(challenge_bytes(msg['nonce'],profile['fp'])).hex()
        channel.control(dict(type='proof',signature=signature))
        kind,msg=channel.receive()
        if kind!=b'J' or msg.get('type')!='welcome' or msg.get('version') not in (1,2):raise ProtocolError('Acesso permanente não aceito.')
        channel.version=msg['version']
        if not isinstance(msg.get('permissions'),dict) or not isinstance(msg.get('monitors'),list) or not 1<=len(msg['monitors'])<=32:raise ProtocolError('Resposta inválida.')
        return Peer(channel,'viewer',event,request,{k:msg['permissions'].get(k) is True for k in ('control','clipboard','audio')},monitors=msg['monitors'])
    except BaseException:channel.close();raise
