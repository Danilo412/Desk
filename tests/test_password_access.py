"""Synthetic password access over real loopback TLS; never injects desktop input."""
import json,threading,time
from types import SimpleNamespace
import pytest
from novoacesso.identity import IdentityStore
from novoacesso.wire import AuthorizationError,ProtocolError,connect_invitation
from novoacesso.session import HostService,join,Peer

PASSWORD='synthetic-Desk-test-phrase'

def configured(tmp_path):
    identity=IdentityStore(tmp_path);identity.password_access.set_password(PASSWORD);identity.password_access.enable(True)
    return identity

def test_password_is_disabled_until_owner_enables_and_is_never_stored_in_plaintext(tmp_path):
    identity=IdentityStore(tmp_path);identity.password_access.set_password(PASSWORD)
    assert identity.password_access.information()['configured'] and not identity.password_access.information()['enabled']
    assert PASSWORD not in json.dumps(identity.data) and PASSWORD.encode() not in identity.path.read_bytes()
    with pytest.raises(AuthorizationError):identity.password_access.verify(PASSWORD)
    identity.password_access.enable(True);revision=identity.password_access.verify(PASSWORD)
    assert identity.password_access.authorized(revision)
    loaded=IdentityStore(tmp_path);assert loaded.password_access.verify(PASSWORD)==revision

@pytest.mark.parametrize('password',['short','',None,'a'*129,'\ud800'*12])
def test_invalid_password_cannot_be_configured(tmp_path,password):
    identity=IdentityStore(tmp_path)
    with pytest.raises((ValueError,UnicodeError)):identity.password_access.set_password(password)
    assert not identity.password_access.information()['configured']

def test_salt_differs_between_hosts_and_password_rotation_revokes_previous_revision(tmp_path):
    first=configured(tmp_path/'one');second=configured(tmp_path/'two')
    assert first.password_access.snapshot()['verifier']!=second.password_access.snapshot()['verifier']
    old=first.password_access.verify(PASSWORD)
    first.password_access.set_password('another-synthetic-test-phrase')
    assert not first.password_access.authorized(old) and not first.password_access.information()['enabled']
    first.password_access.enable(True)
    with pytest.raises(AuthorizationError):first.password_access.verify(PASSWORD)
    assert first.password_access.verify('another-synthetic-test-phrase')!=old
    first.password_access.remove();assert not first.password_access.information()['configured']

def test_five_failures_are_limited_across_attempts_until_window_expires(tmp_path):
    identity=configured(tmp_path);clock=[1.];identity.password_access.clock=lambda:clock[0]
    for _ in range(5):
        with pytest.raises(AuthorizationError):identity.password_access.verify('a-wrong-synthetic-password')
    with pytest.raises(AuthorizationError,match='cinco minutos'):identity.password_access.verify(PASSWORD)
    clock[0]=302.;assert identity.password_access.verify(PASSWORD)>0

def test_tampered_verifier_fails_closed_without_remote_kdf_parameters(tmp_path):
    identity=configured(tmp_path);identity.data['password_access']['salt']='not-a-salt'
    with pytest.raises(AuthorizationError):identity.password_access.verify(PASSWORD)
    assert not identity.password_access.information()['enabled']

class Backend:
    def monitors(self):return [dict(left=0,top=0,width=1920,height=1080)]

def host(tmp_path,identity=None):
    identity=identity or configured(tmp_path);events=[];consents=[];established=[]
    def request(kind,data,timeout):consents.append(kind);return False
    value=HostService(Backend(),lambda *args:events.append(args),request,dict(control=False,clipboard=False,audio=False),identity)
    def establish(channel,monitors,device_public=None,authorization_check=None):
        assert authorization_check is not None and authorization_check()
        established.append(authorization_check)
        channel.control(dict(type='welcome',version=channel.version,permissions=value.permissions,monitors=monitors))
    value.establish=establish
    token=value.start('127.0.0.1',bind_address='127.0.0.1')
    return value,token,consents,established,events

def test_new_untrusted_client_joins_by_password_over_pinned_tls_without_owner_consent(tmp_path):
    server,token,consents,established,events=host(tmp_path)
    prompts=[]
    try:
        client=join(token,lambda *args:None,lambda kind,data,timeout:prompts.append(kind) or PASSWORD)
        assert client.channel.sock.version()=='TLSv1.3' and prompts==['access_password']
        assert not consents and len(established)==1 and not client.permissions['control']
        assert PASSWORD not in repr(events)
        server.identity.password_access.enable(False);assert not established[0]()
        client.close()
    finally:server.stop()

def test_wrong_password_never_establishes_or_requests_local_consent(tmp_path):
    server,token,consents,established,events=host(tmp_path)
    try:
        with pytest.raises(AuthorizationError):join(token,lambda *args:None,lambda *args:'wrong-synthetic-password')
        assert not consents and not established and PASSWORD not in repr(events)
    finally:server.stop()

def test_cancelled_password_prompt_never_establishes(tmp_path):
    server,token,consents,established,events=host(tmp_path)
    try:
        with pytest.raises(ConnectionAbortedError):join(token,lambda *args:None,lambda *args:None)
        assert not consents and not established
    finally:server.stop()

def test_wrong_tls_fingerprint_rejects_before_password_prompt(tmp_path):
    from novoacesso.relay import token_encode
    from novoacesso.wire import parse_invitation
    server,token,consents,established,events=host(tmp_path);data=parse_invitation(token);data['fp']='0'*64
    prompts=[]
    try:
        with pytest.raises((ProtocolError,OSError)):join(token_encode('NA1-',data),lambda *args:None,lambda *args:prompts.append(1) or PASSWORD)
        assert not prompts and not established
    finally:server.stop()

def test_old_client_keeps_manual_consent_when_password_feature_not_negotiated(tmp_path):
    server,token,consents,established,events=host(tmp_path);channel=None
    try:
        channel,data=connect_invitation(token);channel.control(dict(type='hello',min=1,max=2,secret=data['secret']))
        with pytest.raises((ConnectionError,OSError)):channel.receive()
        assert consents==['consent'] and not established
    finally:
        if channel:channel.close()
        server.stop()

def test_disabled_password_access_keeps_consent_required(tmp_path):
    identity=configured(tmp_path);identity.password_access.enable(False)
    server,token,consents,established,events=host(tmp_path,identity);prompts=[]
    try:
        with pytest.raises((ProtocolError,OSError)):join(token,lambda *args:None,lambda *args:prompts.append(1) or PASSWORD)
        assert not prompts and consents==['consent'] and not established
    finally:server.stop()

def test_revoked_password_rejects_host_input_before_injection(tmp_path):
    identity=configured(tmp_path);revision=identity.password_access.verify(PASSWORD);inputs=[]
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def control(self,value):pass
        def close(self):self.closed.set()
    peer=Peer(Channel(),'host',lambda *a:None,lambda *a:None,{'control':True},SimpleNamespace(input=inputs.append,release=lambda:None))
    peer.authorization_check=lambda:identity.password_access.authorized(revision)
    identity.password_access.enable(False)
    peer.apply_input(dict(event='key',vk=65,down=True))
    assert not inputs and peer.closed.is_set()

def test_owner_ui_requires_confirmation_and_does_not_enable_on_cancel(monkeypatch):
    from novoacesso.app import MainWindow
    from PySide6.QtWidgets import QMessageBox
    window=MainWindow()
    try:
        window.identity.password_access.set_password(PASSWORD)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.No)
        window.password_access_changed(True)
        assert not window.identity.password_access.information()['enabled']
        assert not window.password_access_enabled.isChecked()
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
        window.prepare_address=lambda:None
        window.password_access_changed(True)
        assert window.identity.password_access.information()['enabled']
        window.password_access_changed(False)
        assert not window.identity.password_access.information()['enabled']
    finally:window.identity.password_access.remove();window.quit_application()

def test_revoked_password_automatically_closes_idle_session(tmp_path):
    identity=configured(tmp_path);revision=identity.password_access.verify(PASSWORD)
    class Channel:
        version=2;io_thread=None
        def __init__(self):self.closed=threading.Event()
        def control(self,value):pass
        def close(self):self.closed.set()
    peer=Peer(Channel(),'host',lambda *a:None,lambda *a:None,{},SimpleNamespace(release=lambda:None))
    peer.authorization_check=lambda:identity.password_access.authorized(revision)
    thread=threading.Thread(target=peer._authorization_watch,daemon=True);thread.start()
    identity.password_access.remove()
    assert peer.closed.wait(1);thread.join(1);assert not thread.is_alive()

def test_wrong_nonce_never_establishes_password_session(tmp_path):
    server,token,consents,established,events=host(tmp_path);channel=None
    try:
        channel,data=connect_invitation(token)
        channel.control(dict(type='hello',min=1,max=2,secret=data['secret'],password_supported=1))
        kind,challenge=channel.receive();assert challenge['type']=='password_required'
        channel.control(dict(type='access_password',nonce='0'*64,password=PASSWORD))
        kind,denied=channel.receive();assert denied['type']=='denied'
        assert not consents and not established
    finally:
        if channel:channel.close()
        server.stop()
