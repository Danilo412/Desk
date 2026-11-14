import asyncio,time
from types import SimpleNamespace
import pytest
from PIL import Image
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow
from novoacesso.relay import token_encode,token_decode,validate_endpoint
from novoacesso.network_config import use_shipped_relay,refresh_profile
from novoacesso.ice_policy import create_peer

KEY='pk_live_'+'a'*32
def endpoint(password='test-only-old'):
    return validate_endpoint(dict(mode='metered',api_key=KEY,ice_servers=[dict(urls=['turn:free.expressturn.com:3478?transport=udp'],username='test-only-user',credential=password)]))

def test_migrate_rejected_cached_config_only_for_same_provider():
    old=token_encode('NAR1-',endpoint());cloud=dict(public_key=KEY,relay_validated_at=int(time.time()),config_revision='new-configuration')
    assert use_shipped_relay(old,cloud,{})
    assert not use_shipped_relay(old,cloud,{'shipped_relay_revision':'new-configuration'})
    assert not use_shipped_relay(old,cloud,{'relay_customized':True})
    assert not use_shipped_relay(old,dict(cloud,public_key='pk_live_'+'b'*32),{})

@pytest.mark.parametrize('prefix',['NAU1-','NA1-'])
def test_saved_transport_refresh_preserves_target_and_authorization(prefix):
    original=dict(v=1,host='rms.metered.ca',port=443,fp='ab'*32,secret='s'*40,expires=int(time.time())+600,relay=dict(endpoint(),room='c'*64,route='d'*40))
    token=token_encode(prefix,original);refreshed=refresh_profile(token,endpoint('test-only-new'))
    data=token_decode(prefix,refreshed)
    assert {k:v for k,v in data.items() if k!='relay'}=={k:v for k,v in original.items() if k!='relay'}
    assert data['relay']['room']==original['relay']['room'] and data['relay']['route']==original['relay']['route']
    assert data['relay']['ice_servers']==endpoint('test-only-new')['ice_servers']
    unrelated=endpoint();unrelated['api_key']='pk_live_'+'b'*32
    assert refresh_profile(token,unrelated)==token

def test_authorized_control_starts_and_manual_view_only_is_preserved():
    window=MainWindow();sent=[]
    peer=SimpleNamespace(role='viewer',permissions={'control':False},send=sent.append)
    window.peer=peer;window.tabs.setCurrentIndex(1);window.show()
    try:
        window.apply_permissions();assert not window.canvas.allow_control
        peer.permissions['control']=True;window.apply_permissions()
        assert window.control.isChecked() and window.canvas.allow_control
        window.canvas.set_frame(Image.new('RGB',(640,360),'white'));QTest.qWait(40)
        QTest.mouseClick(window.canvas,Qt.MouseButton.LeftButton,pos=QPoint(window.canvas.width()//2,window.canvas.height()//2))
        assert any(m.get('type')=='input' and m.get('event')=='button' and m.get('down') for m in sent)
        window.control.setChecked(False);window.apply_permissions();assert not window.canvas.allow_control
        peer.permissions['control']=False;window.apply_permissions();assert not window.control.isEnabled()
        peer.permissions['control']=True;window.apply_permissions();assert window.canvas.allow_control
    finally:window.peer=None;window.close()

def test_forced_relay_cannot_succeed_using_local_candidates():
    async def test():
        pc=create_peer([{'urls':['stun:free.expressturn.com:3478']}],relay_only=True)
        try:
            pc.createDataChannel('test-only')
            connection=pc.sctp.transport.transport._connection
            # No TURN configured: forcing relay must fail, never use localhost.
            with pytest.raises(ConnectionError):await connection.get_component_candidates(1,['127.0.0.1'],timeout=.01)
            assert not connection._protocols
        finally:await pc.close()
    asyncio.run(test())

def test_turn_rejection_is_sanitized(monkeypatch):
    from novoacesso.turn_validation import allocation
    import aioice.ice
    async def reject(**kwargs):raise RuntimeError('401 test-only-user test-only-old')
    monkeypatch.setattr(aioice.ice,'relayed_candidate',reject)
    result=asyncio.run(allocation(endpoint()['ice_servers'][0],'tcp'))
    assert not result['passed'] and result['category']=='authentication'
    assert 'test-only-user' not in str(result) and 'test-only-old' not in str(result)

def test_ice_keeps_relay_and_direct_but_skips_unresponsive_secondary_interface(monkeypatch):
    import copy
    import aioice.ice as ice
    from novoacesso.ice_policy import gather_component
    cancelled=[]
    async def stun(protocol,server):
        if protocol.local_candidate.host=='127.0.0.2':
            try:await asyncio.sleep(60)
            finally:cancelled.append(True)
        candidate=copy.copy(protocol.local_candidate);candidate.type='srflx'
        return candidate,None
    async def turn(**kwargs):
        await asyncio.sleep(.03)
        return ice.Candidate(foundation='test',component=1,transport='udp',priority=1,host='127.0.0.1',port=12345,type='relay'),None
    monkeypatch.setattr(ice,'server_reflexive_candidate',stun);monkeypatch.setattr(ice,'relayed_candidate',turn)
    async def test():
        connection=ice.Connection(ice_controlling=True,stun_server=('unused',3478),turn_server=('unused',3478))
        try:
            candidates=await asyncio.wait_for(gather_component(connection,1,['127.0.0.1','127.0.0.2'],timeout=3),2)
            assert {'host','srflx','relay'}=={c.type for c in candidates}
            assert len([c for c in candidates if c.type=='host'])==2 and cancelled
        finally:await connection.close()
    asyncio.run(test())

def test_tcp_turn_fallback_when_udp_is_blocked(monkeypatch):
    import aioice.ice as ice
    from novoacesso.ice_policy import gather_component
    attempted=[]
    async def turn(**kwargs):
        attempted.append(kwargs['turn_transport'])
        if kwargs['turn_transport']=='udp':raise TimeoutError('simulated blocked UDP')
        return ice.Candidate(foundation='test',component=1,transport='udp',priority=1,host='127.0.0.1',port=12345,type='relay'),None
    monkeypatch.setattr(ice,'relayed_candidate',turn)
    async def test():
        connection=ice.Connection(ice_controlling=True)
        connection._novo_turn_options=[dict(turn_server=('unused',3478),turn_username='test',turn_password='test',turn_ssl=False,turn_transport=p) for p in ('udp','tcp')]
        try:
            candidates=await gather_component(connection,1,['127.0.0.1'])
            assert sorted(attempted)==['tcp','udp'] and any(c.type=='relay' for c in candidates)
        finally:await connection.close()
    asyncio.run(test())

def test_relay_only_does_not_close_shared_ice_data_queue(monkeypatch):
    import aioice.ice as ice
    candidate=ice.Candidate(foundation='test',component=1,transport='udp',priority=1,host='127.0.0.1',port=12345,type='relay')
    class RelayProtocol:
        local_candidate=candidate
        async def close(self):pass
    async def turn(**kwargs):return candidate,RelayProtocol()
    monkeypatch.setattr(ice,'relayed_candidate',turn)
    async def test():
        pc=create_peer(endpoint()['ice_servers'],relay_only=True)
        try:
            pc.createDataChannel('test')
            connection=pc.sctp.transport.transport._connection
            candidates=await connection.get_component_candidates(1,['127.0.0.1'])
            assert candidates and all(c.type=='relay' for c in candidates)
            assert all(p.local_candidate.type=='relay' for p in connection._protocols)
            assert connection._queue.empty()
        finally:await pc.close()
    asyncio.run(test())

def test_late_turn_allocation_is_retained_without_inserting_eof(monkeypatch):
    import aioice.ice as ice
    from novoacesso.ice_policy import gather_component
    async def test():
        connection=ice.Connection(ice_controlling=True)
        connection._novo_turn_options=[dict(turn_server=('unused',3478),turn_username='test',turn_password='test',turn_ssl=False,turn_transport=p) for p in ('udp','tcp')]
        class Protocol:
            def __init__(self,candidate):self.local_candidate=candidate
            async def close(self):connection.data_received(None,None)
        async def turn(**kwargs):
            if kwargs['turn_transport']=='tcp':
                try:await asyncio.sleep(60)
                except asyncio.CancelledError:pass  # Completion raced cancellation.
            candidate=ice.Candidate(foundation=kwargs['turn_transport'],component=1,transport='udp',priority=1,host='127.0.0.1',port=12345,type='relay')
            return candidate,Protocol(candidate)
        monkeypatch.setattr(ice,'relayed_candidate',turn)
        try:
            candidates=await gather_component(connection,1,[])
            assert len(candidates)==len(connection._protocols)==2
            assert connection._queue.empty()
        finally:await connection.close()
    asyncio.run(test())
