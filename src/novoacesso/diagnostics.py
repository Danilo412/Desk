"""Diagnóstico local com imagem sintética: não captura nem controla o desktop."""
from contextlib import nullcontext
import hashlib
import secrets
import tempfile
import time
from pathlib import Path
from PIL import Image
from .codec import ScreenEncoder,ScreenDecoder
from .session import HostService,join

def numeric_test(key):
    from .numeric_invite import NumericInvite,resolve_code,normalize_code
    import threading
    host=peer=directory=None;checks={};ready=threading.Event();offers=[];received=[];consents=[]
    class Synthetic:
        def monitors(self):return [dict(left=0,top=0,width=64,height=64)]*2
        def capture_source(self):return nullcontext()
        def capture(self,*args):return Image.new('RGB',(64,64),(40,130,80))
        def release(self):pass
    def request(kind,data,timeout):
        if kind=='consent':consents.append(True);return True
        return None
    try:
        host=HostService(Synthetic(),lambda *a:None,request,dict(control=False,clipboard=False,audio=False))
        token=host.start('127.0.0.1',bind_address='127.0.0.1')
        def event(kind,data):
            if kind=='numeric_ready':offers.append(data);ready.set()
        directory=NumericInvite(token,key,event).start()
        if not ready.wait(20):raise TimeoutError('Não foi possível registrar o código numérico.')
        code=offers[0]['code'];assert len(normalize_code(code))==12;checks['twelve_digit_code']=True
        resolved=resolve_code(code,key);assert resolved==token;checks['public_directory_roundtrip']=True
        peer=join(resolved,lambda k,d:received.append(k),request);peer.start()
        deadline=time.monotonic()+10
        while 'frame' not in received and time.monotonic()<deadline:time.sleep(.05)
        assert 'frame' in received and consents==[True]
        checks['approval_required']=True;checks['synthetic_screen_tls']=peer.channel.sock.version()=='TLSv1.3'
        return dict(passed=all(checks.values()),checks=checks,scope='Diretório público real; sessão sintética em localhost. Não captura o desktop nem valida o relay de dados.')
    except Exception as ex:return dict(passed=False,checks=checks,error=(type(ex).__name__+': '+str(ex)).replace(key,'[chave]'))
    finally:
        if directory:directory.stop();directory.thread.join(3)
        if peer:peer.close();peer.wait_for_workers()
        if host:host.stop()

def internet_test(key,ice_servers=None,force_relay=False):
    """Exercita o serviço real somente com imagens e arquivos sintéticos."""
    from .identity import IdentityStore
    from .relay import endpoint_from_token
    from .unattended import TrustedHost
    checks={};host=peer=None;timings=[]
    class Synthetic:
        def __init__(self):self.inputs=[]
        def monitors(self):return [dict(left=0,top=0,width=64,height=64)]*2
        def capture_source(self):return nullcontext()
        def capture(self,*args):return Image.new('RGB',(64,64),(40,130,80))
        def release(self):pass
        def input(self,data):self.inputs.append(data)
    def wait(predicate,timeout=40):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.05)
        raise TimeoutError('Serviço de internet não concluiu o diagnóstico no prazo.')
    try:
        endpoint=endpoint_from_token(key)
        if ice_servers:
            from .relay import validate_endpoint
            endpoint=validate_endpoint(dict(endpoint,ice_servers=ice_servers))
        if force_relay:
            from .relay import validate_endpoint
            endpoint=validate_endpoint(dict(endpoint,relay_only=True))
        with tempfile.TemporaryDirectory(prefix='novoacesso-internet-') as tmp:
            base=Path(tmp);identity=IdentityStore(base/'host');viewer=IdentityStore(base/'viewer')
            def request(kind,data,timeout):return True if kind=='consent' else str(base/'received.bin')
            for trusted in (False,True):
                events=[];received=[]
                if trusted:identity.configure(unattended=True);identity.trust(viewer.public,'diagnóstico sintético')
                desktop=Synthetic()
                host=(TrustedHost if trusted else HostService)(desktop,lambda k,d:events.append((k,d)),request,dict(control=False,clipboard=False,audio=False),identity=identity,relay=endpoint)
                token=host.start('unused');wait(lambda:any(k=='relay_ready' for k,d in events))
                peer=join(token,lambda k,d:received.append((k,d)),request,identity=viewer);peer.start()
                wait(lambda:any(k=='frame' for k,d in received))
                assert peer.channel.sock.version()=='TLSv1.3'
                if force_relay:
                    assert peer.channel.sock.outer.candidate_types and all(tuple(pair)==('relay','relay') for pair in peer.channel.sock.outer.candidate_types)
                    assert host.peer.channel.sock.outer.candidate_types and all(tuple(pair)==('relay','relay') for pair in host.peer.channel.sock.outer.candidate_types)
                    checks['both_endpoints_turn_relay_only']=True
                peer.send(dict(type='chat',text='diagnóstico sintético'))
                wait(lambda:any(k=='chat' for k,d in events))
                checks['trusted_reconnect' if trusted else 'invitation_tls_screen_chat']=True
                host.peer.set_permissions(dict(control=True))
                wait(lambda:peer.permissions.get('control'))
                peer.send(dict(type='input',event='move',x=.25,y=.75))
                wait(lambda:bool(desktop.inputs));assert desktop.inputs[-1]['event']=='move'
                checks['authorized_control_messages']=True
                host.peer.set_permissions(dict(control=False))
                wait(lambda:not peer.permissions.get('control'))
                timings.append(dict(trusted=trusted,host=host.peer.channel.sock.outer.timings,viewer=peer.channel.sock.outer.timings))
                if not trusted:
                    source=base/'synthetic.bin';data=secrets.token_bytes(1024*1024);source.write_bytes(data)
                    peer.send_file(source);wait(lambda:(base/'received.bin').exists(),60)
                    assert hashlib.sha256((base/'received.bin').read_bytes()).digest()==hashlib.sha256(data).digest()
                    checks['file_1mib_sha256']=True
                peer.close();peer.wait_for_workers();peer=None;host.stop();host=None
        return dict(passed=True,checks=checks,forced_relay=force_relay,timings=timings,scope='Serviço público, conteúdo sintético, duas instâncias no mesmo computador. '+('Rota TURN comprovada em ambas as pontas.' if force_relay else 'Rota TURN não forçada.'))
    except Exception as ex:return dict(passed=False,checks=checks,error=(type(ex).__name__+': '+str(ex)).replace(key,'[chave]'))
    finally:
        if peer:peer.close();peer.wait_for_workers()
        if host:host.stop()

def self_test():
    checks={};host=peer=relay=None
    class SyntheticDesktop:
        def __init__(self):self.counter=0;self.inputs=[]
        def monitors(self):return [dict(left=0,top=0,width=64,height=64)]*2
        def capture_source(self):return nullcontext()
        def capture(self,*args):self.counter+=1;return Image.new("RGB",(64,64),(self.counter%255,130,80))
        def input(self,event):self.inputs.append(event)
        def release(self):pass
    def wait(predicate):
        end=time.monotonic()+8
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.02)
        raise RuntimeError("Tempo limite no diagnóstico local.")
    try:
        enc=ScreenEncoder();dec=ScreenDecoder();image=Image.new("RGB",(64,64),(30,130,80))
        packet,_=enc.encode(image,"deflate");assert dec.decode(packet).tobytes()==image.tobytes();checks["deflate_exact"]=True
        packet,_=enc.encode(image,"vp8");decoded=dec.decode(packet);assert decoded.size==image.size
        assert sum(abs(a-b) for a,b in zip(decoded.getpixel((20,20)),image.getpixel((20,20))))<30;checks["vp8_roundtrip"]=True
        with tempfile.TemporaryDirectory(prefix="novoacesso-test-") as tmp:
            destination=Path(tmp)/"recebido.bin";events=[];desktop=SyntheticDesktop()
            def request(kind,data,timeout):return True if kind=="consent" else str(destination)
            host=HostService(desktop,lambda k,d:events.append((k,d)),request,dict(control=False,clipboard=False,audio=False))
            token=host.start("127.0.0.1",bind_address="127.0.0.1")
            received=[];peer=join(token,lambda k,d:received.append((k,d)),request);peer.start()
            wait(lambda:any(k=="frame" for k,d in received))
            assert peer.channel.sock.version()=="TLSv1.3";checks["tls13_pinned_loopback"]=True
            peer.send(dict(type="input",event="key",vk=65,down=True));time.sleep(.1)
            assert desktop.inputs==[];checks["control_denied_by_default"]=True
            peer.send(dict(type="chat",text="teste local"));wait(lambda:any(k=="chat" and d["text"]=="teste local" for k,d in events));checks["chat"]=True
            source=Path(tmp)/"origem.bin";data=secrets.token_bytes(100123);source.write_bytes(data);peer.send_file(source)
            wait(destination.exists);assert hashlib.sha256(destination.read_bytes()).digest()==hashlib.sha256(data).digest();checks["file_transfer_sha256"]=True
            checks["synthetic_screen_over_tls"]=True
            peer.close();peer.wait_for_workers();host.stop()
            from .identity import IdentityStore
            from .relay import endpoint_from_token
            from .relay_server import RelayServer
            from .unattended import TrustedHost
            store=IdentityStore(Path(tmp)/'host-identity');controller=IdentityStore(Path(tmp)/'controller-identity')
            store.configure(unattended=True);store.trust(controller.public,'diagnóstico local')
            fingerprint=store.tls_identity()[1]
            assert IdentityStore(store.root).tls_identity()[1]==fingerprint;checks['persistent_identity']=True
            relay=RelayServer(IdentityStore(Path(tmp)/'relay-identity'))
            endpoint=endpoint_from_token(relay.start('127.0.0.1',0,'127.0.0.1'))
            host=TrustedHost(desktop,lambda *a:None,lambda *a:False,dict(control=False,clipboard=False,audio=False),identity=store,relay=endpoint)
            token=host.start('relay');wait(lambda:bool(relay.slots));received=[]
            peer=join(token,lambda k,d:received.append((k,d)),lambda *a:None,identity=controller);peer.start()
            wait(lambda:any(k=='frame' for k,d in received))
            assert peer.channel.sock.version()=='TLSv1.3';checks['end_to_end_tls_over_relay']=True
            checks['unattended_trusted_device']=True
            store.revoke(controller.public);wait(lambda:host.peer.closed.is_set());checks['device_revocation']=True
        return dict(passed=True,checks=checks,scope="Localhost, conteúdo sintético; não substitui ensaio em dois computadores ou verificação de áudio e entrada física.")
    except Exception as ex:return dict(passed=False,checks=checks,error=type(ex).__name__+": "+str(ex))
    finally:
        if peer:peer.close()
        if host:host.stop()
        if relay:relay.stop()
