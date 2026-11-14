import json,sys,subprocess,threading
from pathlib import Path
import pytest
from novoacesso.identity import IdentityStore
from novoacesso.device_address import address_for_public,format_address,offer_bytes,verify_offer
from novoacesso.numeric_invite import NumericInvite,resolve_address
from novoacesso.wire import make_invitation,ProtocolError
from test_numeric_invite import Hub

def token_for(store):return make_invitation('127.0.0.1',4433,store.certificate_fingerprint)[1]

def test_address_persists_with_existing_identity(tmp_path):
    store=IdentityStore(tmp_path/'host');value=store.desk_address
    assert len(value)==12 and value.isascii() and value.isdecimal()
    assert IdentityStore(store.root).desk_address==value
    assert IdentityStore(tmp_path/'other').desk_address!=value

def test_gui_close_reopen_and_disconnect_keep_same_number(tmp_path):
    script=Path(__file__).with_name('fixed_address_probe.py')
    runs=[subprocess.run([sys.executable,str(script),str(tmp_path/'device')],capture_output=True,timeout=25,check=True) for _ in range(2)]
    a,b=[json.loads(p.stdout) for p in runs]
    assert a['pid']!=b['pid']
    assert a['before']==a['after_disconnect']==b['before']==b['after_disconnect']
    assert len(a['before'].replace(' ',''))==12

def test_signed_offer_binds_number_token_and_request_challenge(tmp_path):
    store=IdentityStore(tmp_path/'host');token=token_for(store);nonce='ab'*16
    signature=store.signing_key.sign(offer_bytes(store.desk_address,token,nonce,store.public)).hex()
    assert verify_offer(store.desk_address,token,nonce,store.public,signature)==store.public
    for code,changed_token,changed_nonce in [('000000000000',token,nonce),(store.desk_address,token_for(store),nonce),(store.desk_address,token,'cd'*16)]:
        with pytest.raises(ProtocolError):verify_offer(code,changed_token,changed_nonce,store.public,signature)

def test_pinned_identity_survives_restart_and_refuses_replacement(tmp_path,monkeypatch):
    from novoacesso import device_address
    host=IdentityStore(tmp_path/'host');viewer=IdentityStore(tmp_path/'viewer');attacker=IdentityStore(tmp_path/'other')
    code=host.desk_address;viewer.pin_address(code,host.public)
    restored=IdentityStore(viewer.root);assert restored.address_peer(code)==host.public
    # Even a hypothetical short-number collision must not replace a full key pin.
    monkeypatch.setattr(device_address,'address_for_public',lambda public:code)
    with pytest.raises(ProtocolError,match='mudou'):restored.pin_address(code,attacker.public)
    assert IdentityStore(viewer.root).address_peer(code)==host.public

def test_host_cannot_advertise_another_tls_identity(tmp_path):
    host=IdentityStore(tmp_path/'host');other=IdentityStore(tmp_path/'other')
    with pytest.raises(ProtocolError,match='não pertence'):NumericInvite(token_for(other),'key',lambda *a:None,identity=host)

def test_same_number_resolves_new_transport_after_host_restart(tmp_path):
    hub=Hub();host_path=tmp_path/'host';expected=None;tokens=[];codes=[]
    for _ in range(2):
        store=IdentityStore(host_path);token=token_for(store);ready=threading.Event()
        host=NumericInvite(token,'synthetic-key',lambda *a:ready.set(),hub.client,identity=store).start()
        try:
            assert ready.wait(5)
            result=resolve_address(format_address(store.desk_address),'synthetic-key',timeout=3,client_factory=hub.client,expected_public=expected)
            assert result['token']==token and result['public']==store.public
            expected=store.public;tokens.append(token);codes.append(result['code'])
        finally:host.stop();host.thread.join(5)
    assert codes[0]==codes[1] and tokens[0]!=tokens[1] and not hub.clients

def test_fixed_lookup_rejects_unsigned_legacy_response(tmp_path):
    hub=Hub();ready=threading.Event();store=IdentityStore(tmp_path/'host')
    legacy=NumericInvite(token_for(store),'synthetic-key',lambda *a:ready.set(),hub.client).start()
    try:
        assert ready.wait(5)
        with pytest.raises(ProtocolError,match='verificada'):
            resolve_address(legacy.code,'synthetic-key',timeout=.4,client_factory=hub.client)
    finally:legacy.stop();legacy.thread.join(5)

def test_fixed_lookup_rejects_tampered_signature(tmp_path):
    hub=Hub();ready=threading.Event();store=IdentityStore(tmp_path/'host')
    class TamperingClient:
        def __init__(self,wrapped):self.wrapped=wrapped
        def __getattr__(self,name):return getattr(self.wrapped,name)
        async def send(self,to,data):
            if data.get('kind')=='numeric_offer':data=dict(data,signature='00'*64)
            return await self.wrapped.send(to,data)
    host=NumericInvite(token_for(store),'synthetic-key',lambda *a:ready.set(),lambda **k:TamperingClient(hub.client()),identity=store).start()
    try:
        assert ready.wait(5)
        with pytest.raises(ProtocolError,match='verificada'):
            resolve_address(store.desk_address,'synthetic-key',timeout=.4,client_factory=hub.client)
    finally:host.stop();host.thread.join(5)
