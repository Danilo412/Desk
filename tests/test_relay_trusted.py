import time
import pytest
from novoacesso.identity import IdentityStore,verify_proof,challenge_bytes
from novoacesso.relay import endpoint_from_token,token_encode
from novoacesso.relay_server import RelayServer
from novoacesso.session import HostService,join
from novoacesso.unattended import TrustedHost,parse_profile
from test_session import FakeDesktop,wait_for

@pytest.fixture
def relay(tmp_path):
    server=RelayServer(IdentityStore(tmp_path/'relay-state'));token=server.start('127.0.0.1',0,'127.0.0.1')
    yield server,endpoint_from_token(token)
    server.stop()

def test_relay_screen_chat_file_tls_and_reject_outer_certificate(relay,tmp_path):
    server,endpoint=relay;events=[];received=[];backend=FakeDesktop();controller=IdentityStore(tmp_path/'controller')
    def request(kind,data,timeout):return True if kind=='consent' else str(tmp_path/'received.bin')
    host=HostService(backend,lambda k,d:events.append((k,d)),request,{'control':False,'clipboard':False,'audio':False},relay=endpoint)
    token=host.start('unused');peer=None
    try:
        wait_for(lambda:server.slots)
        peer=join(token,lambda k,d:received.append((k,d)),request,identity=controller);peer.start()
        wait_for(lambda:any(k=='frame' for k,d in received))
        assert peer.channel.sock.version()=='TLSv1.3'
        assert host.peer.device_public==controller.public
        peer.send(dict(type='chat',text='relayed secret'))
        wait_for(lambda:any(k=='chat' and d['text']=='relayed secret' for k,d in events))
        file=tmp_path/'sent.bin';file.write_bytes(b'relay-file'*10000);peer.send_file(file)
        wait_for(lambda:(tmp_path/'received.bin').exists())
        assert (tmp_path/'received.bin').read_bytes()==file.read_bytes()
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_unattended_trusted_persistence_untrusted_and_revocation(tmp_path):
    store=IdentityStore(tmp_path/'host');client=IdentityStore(tmp_path/'client');stranger=IdentityStore(tmp_path/'stranger')
    store.configure(unattended=True);store.trust(client.public,'my controller')
    original_fp=store.tls_identity()[1]
    reloaded=IdentityStore(tmp_path/'host');assert reloaded.tls_identity()[1]==original_fp and reloaded.trusted(client.public)
    backend=FakeDesktop();events=[];host=TrustedHost(backend,lambda k,d:events.append((k,d)),lambda *args:pytest.fail('Unattended must not ask for consent'),{'control':True,'clipboard':False,'audio':False},identity=reloaded)
    token=host.start('127.0.0.1',port=0,bind_address='127.0.0.1');peer=None
    try:
        with pytest.raises((ConnectionError,OSError)):join(token,lambda *a:None,lambda *a:None,identity=stranger)
        received=[];peer=join(token,lambda k,d:received.append((k,d)),lambda *a:None,identity=client);peer.start()
        wait_for(lambda:any(k=='frame' for k,d in received))
        peer.send(dict(type='input',event='key',vk=65,down=True));wait_for(lambda:backend.inputs)
        reloaded.revoke(client.public);wait_for(lambda:host.peer.closed.is_set())
        peer.close();peer.wait_for_workers();peer=None
        with pytest.raises((ConnectionError,OSError)):join(token,lambda *a:None,lambda *a:None,identity=client)
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_unattended_over_relay(relay,tmp_path):
    server,endpoint=relay;store=IdentityStore(tmp_path/'host');client=IdentityStore(tmp_path/'client')
    store.configure(unattended=True);store.trust(client.public,'controller')
    host=TrustedHost(FakeDesktop(),lambda *a:None,lambda *a:None,{'control':False},identity=store,relay=endpoint)
    token=host.start('ignored');peer=None;events=[]
    try:
        wait_for(lambda:server.slots)
        peer=join(token,lambda k,d:events.append((k,d)),lambda *a:None,identity=client);peer.start()
        wait_for(lambda:any(k=='frame' for k,d in events))
        assert peer.channel.sock.version()=='TLSv1.3'
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_proof_bound_to_nonce_and_host_certificate(tmp_path):
    client=IdentityStore(tmp_path/'client');nonce='11'*32;fp='22'*32
    signature=client.signing_key.sign(challenge_bytes(nonce,fp)).hex()
    assert verify_proof(client.public,signature,nonce,fp)
    assert not verify_proof(client.public,signature,'33'*32,fp)
    assert not verify_proof(client.public,signature,nonce,'44'*32)

def test_relay_wrong_endpoint_certificate(relay):
    from novoacesso.relay import relay_socket
    server,endpoint=relay;wrong=dict(endpoint,fp='00'*32)
    with pytest.raises(Exception,match='Certificado'):relay_socket(wrong,'aa'*32,'b'*43,'viewer')

def test_relay_access_key_and_room_secret_rejected(relay):
    from novoacesso.relay import relay_socket
    server,endpoint=relay
    with pytest.raises(Exception,match='acesso'):relay_socket(dict(endpoint,access='x'*43),'aa'*32,'b'*43,'viewer')
    host=HostService(FakeDesktop(),lambda *a:None,lambda *a:True,{},relay=endpoint)
    try:
        host.start('ignored');wait_for(lambda:server.slots)
        with pytest.raises(Exception,match='indisponível'):relay_socket(endpoint,host.route['room'],'x'*43,'viewer')
        assert host.peer is None
    finally:host.stop()

def test_persistent_private_state_is_encrypted_and_disabled_host_rejects(tmp_path):
    store=IdentityStore(tmp_path/'host');client=IdentityStore(tmp_path/'client');store.trust(client.public,'client')
    import os
    if os.name=='nt':assert store.data['sign'].encode() not in store.path.read_bytes()
    backend=FakeDesktop();host=TrustedHost(backend,lambda *a:None,lambda *a:None,{},identity=store)
    token=host.start('127.0.0.1',port=0,bind_address='127.0.0.1')
    try:
        with pytest.raises((OSError,ConnectionError)):join(token,lambda *a:None,lambda *a:None,identity=client)
        assert backend.counter==0
    finally:host.stop()

def test_startup_is_user_opt_in_and_points_to_visible_tray_app(monkeypatch):
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    from novoacesso import startup
    calls=[]
    fake=SimpleNamespace(HKEY_CURRENT_USER=1,REG_SZ=1,CreateKey=lambda *args:nullcontext('key'),
        SetValueEx=lambda *args:calls.append(('set',args)),DeleteValue=lambda *args:calls.append(('delete',args)))
    monkeypatch.setitem(sys.modules,'winreg',fake);monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',r'C:\Novo Acesso\NovoAcesso.exe')
    startup.set_autostart(True);startup.set_autostart(False)
    assert calls[0][1][-1]=='"C:\\Novo Acesso\\NovoAcesso.exe" --background'
    assert calls[1][0]=='delete'

def test_unattended_file_receive_uses_explicit_download_folder(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    store=IdentityStore(tmp_path/'host');client=IdentityStore(tmp_path/'client')
    store.configure(unattended=True,unattended_files=True);store.trust(client.public,'controller')
    host=TrustedHost(FakeDesktop(),lambda *a:None,lambda *a:pytest.fail('Não deve pedir destino quando a opção local estiver ativa.'),{},identity=store)
    token=host.start('127.0.0.1',port=0,bind_address='127.0.0.1');peer=None
    try:
        peer=join(token,lambda *a:None,lambda *a:None,identity=client);peer.start()
        file=tmp_path/'upload.bin';file.write_bytes(b'authorized file')
        peer.send_file(file)
        folder=tmp_path/'home/Downloads/NovoAcesso'
        wait_for(lambda:folder.exists() and list(folder.glob('*-upload.bin')))
        assert list(folder.glob('*-upload.bin'))[0].read_bytes()==file.read_bytes()
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_relay_preserves_ssl_write_retry_buffer(monkeypatch,tmp_path):
    import ssl
    from novoacesso import relay_server
    server=RelayServer(IdentityStore(tmp_path/'relay'))
    class Socket:
        def __init__(self):self.data=iter([b'one',b'two',b'']);self.writes=[]
        def setblocking(self,*args):pass
        def pending(self):return 0
        def recv(self,*args):return next(self.data)
        def send(self,data):
            self.writes.append(bytes(data))
            if len(self.writes)==1:raise ssl.SSLWantWriteError()
            assert bytes(data)==b'one'
            return len(data)
    left,right=Socket(),Socket()
    monkeypatch.setattr(relay_server.select,'select',lambda reads,writes,*args:([left] if left in reads else [],list(writes),[]))
    server._bridge(left,right)
    assert right.writes==[b'one',b'one']
