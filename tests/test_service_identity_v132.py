"""Service-identity regression tests; no service activation or desktop input."""
import ctypes,hashlib
from types import SimpleNamespace
import pytest
from novoacesso.service_identity import validate_service_identity
from novoacesso.service_client import WindowsPipe,BrokerClient

CONFIG={'ServicePath':r'C:\Program Files\DeskHost\DeskHost.exe'}
SNAPSHOT=dict(kind=16,state=4,pid=4455,config_kind=16,
              command='"'+CONFIG['ServicePath']+'" --service',account='LocalSystem')

def test_expected_local_system_service_is_accepted_without_process_or_token_access():
    validate_service_identity(CONFIG,SNAPSHOT,4455,0)

@pytest.mark.parametrize('change',[
    {'pid':4456},{'state':1},{'kind':32},{'config_kind':32},
    {'account':'LocalService'},{'account':'a-user'},
    {'command':r'"C:\Users\Someone\DeskHost.exe" --service'},
    {'command':SNAPSHOT['command']+' --other-argument'},
])
def test_wrong_service_identity_is_rejected(change):
    with pytest.raises(OSError):validate_service_identity(CONFIG,dict(SNAPSHOT,**change),4455,0)

def test_console_process_cannot_impersonate_system_service():
    with pytest.raises(OSError):validate_service_identity(CONFIG,SNAPSHOT,4455,1)

def make_pipe():
    def set_pid(handle,pointer):pointer._obj.value=4455;return True
    def set_session(handle,pointer):pointer._obj.value=0;return True
    value=WindowsPipe.__new__(WindowsPipe);value.handle=123
    value.api=SimpleNamespace(GetNamedPipeServerProcessId=set_pid,GetNamedPipeServerSessionId=set_session)
    return value

def test_pipe_identity_pins_scm_process_session_command_account_and_binary(tmp_path,monkeypatch):
    from novoacesso import service_identity
    binary=tmp_path/'DeskHost.exe';binary.write_bytes(b'synthetic service fixture')
    config=dict(ServicePath=str(binary),ServiceHash=hashlib.sha256(binary.read_bytes()).hexdigest())
    snapshot=dict(SNAPSHOT,command='"'+str(binary)+'" --service')
    monkeypatch.setattr(service_identity,'service_identity_snapshot',lambda:snapshot.copy())
    make_pipe().verify_server(config)
    binary.write_bytes(b'replaced')
    with pytest.raises(OSError):make_pipe().verify_server(config)

def test_scm_change_during_verification_is_rejected(tmp_path,monkeypatch):
    from novoacesso import service_identity
    binary=tmp_path/'DeskHost.exe';binary.write_bytes(b'fixture')
    config=dict(ServicePath=str(binary),ServiceHash=hashlib.sha256(binary.read_bytes()).hexdigest())
    snapshots=iter([dict(SNAPSHOT,command='"'+str(binary)+'" --service'),dict(SNAPSHOT,pid=4456,command='"'+str(binary)+'" --service')])
    monkeypatch.setattr(service_identity,'service_identity_snapshot',lambda:next(snapshots))
    with pytest.raises(OSError):make_pipe().verify_server(config)

def test_connection_failure_keeps_bounded_error_code_and_recovers_on_retry():
    attempts=[]
    class Pipe:
        def exchange(self,*args):return b'\0\0'
        def close(self):pass
    def connect(config):
        attempts.append(1)
        if len(attempts)==1:raise OSError(5,'synthetic private error detail')
        return Pipe()
    broker=BrokerClient(connect,{'fixture':True});broker.begin_session()
    assert not broker.available() and broker.last_error_code==5
    assert 'private error detail' not in broker.last_error
    assert broker.available() and broker.last_error_code is None
    broker.end_session()

def test_reauthorization_while_connector_opens_rejects_old_connection():
    closed=[];broker=None
    class Pipe:
        def exchange(self,*args):raise AssertionError('Old connection must not send a request')
        def close(self):closed.append(True)
    def connect(config):broker.end_session();broker.begin_session();return Pipe()
    broker=BrokerClient(connect,{'fixture':True});broker.begin_session()
    assert not broker.available() and closed==[True] and broker.connection is None
    broker.end_session()

def test_service_check_click_always_shows_visible_feedback_without_granting_lease(monkeypatch):
    from novoacesso import service_client
    from novoacesso.app import MainWindow
    monkeypatch.setattr(service_client,'installed_configuration',lambda:None)
    window=MainWindow()
    try:
        window.service_check_button.click()
        assert 'Verificação 1 concluída' in window.service_registration_status.text()
        window.service_check_button.click()
        assert 'Verificação 2 concluída' in window.service_registration_status.text()
        assert 'não instalado' in window.service_registration_status.text() and window.backend is None
    finally:window.quit_application()
