from novoacesso.usage import MonthlyBudget
from novoacesso.identity import IdentityStore
from novoacesso.relay import endpoint_from_token
from novoacesso.relay_server import RelayServer

def test_budget_is_bounded_persistent_and_renews_by_month(tmp_path):
    month=['2026-10'];path=tmp_path/'usage.json'
    budget=MonthlyBudget(path,100,clock=lambda:month[0])
    assert budget.allow(60) and not budget.allow(41) and budget.allow(40)
    reopened=MonthlyBudget(path,100,clock=lambda:month[0]);assert not reopened.allow(1)
    month[0]='2026-11';assert reopened.allow(1)

def test_public_proxy_port_differs_from_private_listener(tmp_path):
    server=RelayServer(IdentityStore(tmp_path/'state'),max_connections=4,max_sessions=1,monthly_byte_limit=1024)
    try:
        token=server.start('127.0.0.1',0,advertise='example.invalid',advertise_port=19321)
        endpoint=endpoint_from_token(token)
        assert endpoint['host']=='example.invalid' and endpoint['port']==19321
        assert server.listener.getsockname()[1]!=endpoint['port']
    finally:server.stop()
