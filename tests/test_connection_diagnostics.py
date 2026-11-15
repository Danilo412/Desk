import json
import pytest
from metered_realtime.errors import SignallingConnectError,ServerRequestError
from novoacesso.numeric_invite import RequestBudget,signalling_error,resolve_address
from novoacesso.wire import ProtocolError

def test_request_budget_recovers_after_window_instead_of_blocking_host_forever():
    now=[0.];budget=RequestBudget(clock=lambda:now[0])
    for i in range(20):assert budget.allow(str(i))
    assert not budget.allow('another') and not budget.allow('0')
    now[0]=10.1
    assert budget.allow('another') and budget.allow('0')

@pytest.mark.parametrize('error,expected',[
    (SignallingConnectError(4010,'quota'),'conexões simultâneas'),
    (SignallingConnectError(4011,'rate'),'Muitas solicitações'),
    (ServerRequestError('over_message_quota','private debug data'),'franquia de mensagens'),
    (ServerRequestError('channel_not_authorized','secret=do-not-display'),'mesma configuração'),
])
def test_provider_limits_are_distinguished_from_offline_computer_without_leaking_error(error,expected):
    text=signalling_error(error)
    assert expected in text and 'do-not-display' not in text and 'debug' not in text

def test_lookup_reports_provider_cap_without_saying_device_is_offline():
    class Capped:
        def __init__(self,**kwargs):pass
        def on(self,kind):return lambda fn:fn
        async def connect(self):raise SignallingConnectError(4010,'quota')
        async def close(self):pass
    with pytest.raises(ProtocolError,match='conexões simultâneas'):
        resolve_address('228784030709','synthetic-key',client_factory=Capped)

def test_transient_lookup_service_failure_remains_retryable():
    class Disconnected:
        def __init__(self,**kwargs):pass
        def on(self,kind):return lambda fn:fn
        async def connect(self):raise OSError('transient failure with private diagnostics')
        async def close(self):pass
    with pytest.raises(ConnectionError,match='serviço de localização'):
        resolve_address('228784030709','synthetic-key',client_factory=Disconnected)

def test_missing_configuration_is_clearly_offline_and_fixed_number_remains(tmp_path,monkeypatch):
    from novoacesso.app import MainWindow
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        before=window.numeric_code.text();window.cloud_signaling_key='';window.prepare_address()
        assert window.numeric_code.text()==before
        assert 'configure a internet' in window.address_caption.text()
        assert 'Falta a configuração' in window.activity.text()
    finally:window.close()

def test_saved_connection_key_restores_number_directory_without_shipped_file(tmp_path,monkeypatch):
    from novoacesso.identity import IdentityStore
    from novoacesso.relay import token_encode
    from novoacesso.app import MainWindow
    store=IdentityStore(tmp_path);config=token_encode('NAR1-',dict(mode='metered',api_key='pk_live_'+'a'*32))
    store.configure(relay_config=config,use_relay=True)
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:assert window.cloud_signaling_key=='pk_live_'+'a'*32
    finally:window.close()
