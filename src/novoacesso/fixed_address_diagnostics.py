"""Two synthetic sessions with a persisted fixed address; no real desktop I/O."""
from pathlib import Path
from contextlib import nullcontext
import tempfile,time
from PIL import Image
from .identity import IdentityStore
from .numeric_invite import NumericInvite,resolve_address
from .relay import validate_endpoint
from .session import HostService,join

def fixed_address_test(key,ice_servers):
    host=peer=directory=None;checks={};approvals=[];numbers=[];tokens=[]
    class Synthetic:
        def monitors(self):return [dict(left=0,top=0,width=64,height=64)]*2
        def capture_source(self):return nullcontext()
        def capture(self,*args):return Image.new('RGB',(64,64),(40,130,80))
        def release(self):pass
    def wait(predicate,seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.03)
        raise TimeoutError('O teste do endereço fixo não terminou no prazo.')
    def request(kind,data,timeout):
        if kind=='consent':approvals.append(True);return True
        return None
    try:
        endpoint=validate_endpoint(dict(mode='metered',api_key=key,ice_servers=ice_servers,relay_only=True))
        with tempfile.TemporaryDirectory(prefix='desk-fixed-address-') as tmp:
            base=Path(tmp)
            for attempt in range(2):
                identity=IdentityStore(base/'host');viewer=IdentityStore(base/'viewer');events=[];received=[]
                host=HostService(Synthetic(),lambda k,d:events.append((k,d)),request,dict(control=False,clipboard=False,audio=False),identity=identity,relay=endpoint)
                token=host.start('unused');wait(lambda:any(k=='relay_ready' for k,d in events))
                directory=NumericInvite(token,key,lambda k,d:events.append((k,d)),identity=identity).start()
                wait(lambda:any(k=='numeric_ready' for k,d in events))
                result=resolve_address(identity.desk_address,key,expected_public=viewer.address_peer(identity.desk_address))
                assert result['public']==identity.public and result['token']==token
                peer=join(result['token'],lambda k,d:received.append((k,d)),request,identity=viewer)
                viewer.pin_address(result['code'],result['public']);peer.start();wait(lambda:any(k=='frame' for k,d in received))
                assert peer.channel.sock.version()=='TLSv1.3'
                assert all(tuple(p)==('relay','relay') for p in peer.channel.sock.outer.candidate_types)
                assert all(tuple(p)==('relay','relay') for p in host.peer.channel.sock.outer.candidate_types)
                assert peer.channel.sock.outer.candidate_types and host.peer.channel.sock.outer.candidate_types
                checks['both_endpoints_turn_relay_only']=True;checks['signed_online_lookup']=True;checks['synthetic_screen_over_tls13']=True
                numbers.append(identity.desk_address);tokens.append(token)
                peer.close();peer.wait_for_workers();peer=None
                directory.stop();directory.thread.join(5);assert not directory.thread.is_alive();directory=None
                host.stop();host=None
            assert numbers[0]==numbers[1] and tokens[0]!=tokens[1]
            assert approvals==[True,True]
            assert IdentityStore(base/'viewer').address_peer(numbers[0])==IdentityStore(base/'host').public
            checks.update(fixed_number_after_host_restart=True,new_transport_same_number=True,approval_required_for_each_normal_session=True,peer_identity_pin_survives_restart=True)
        return dict(passed=True,checks=checks,scope='Serviço público, TURN forçado nas duas pontas, dois ciclos de abertura/conexão com identidades persistidas e conteúdo sintético no mesmo computador.')
    except Exception as ex:
        return dict(passed=False,checks=checks,error_type=type(ex).__name__,scope='Diagnóstico sintético do endereço fixo; falha não equivale a validação.')
    finally:
        if directory:directory.stop();directory.thread.join(5)
        if peer:peer.close();peer.wait_for_workers()
        if host:host.stop()
