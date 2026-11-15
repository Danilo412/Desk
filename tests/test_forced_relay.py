import asyncio
from types import SimpleNamespace
import pytest
from aioice import Candidate,stun
from novoacesso.ice_policy import create_peer
from novoacesso.relay import peer_client_socket
from novoacesso.wire import ProtocolError

def candidate(kind,port):
    return Candidate(foundation=kind,component=1,transport='udp',priority=100,host='203.0.113.12',port=port,type=kind)

def test_forced_relay_does_not_admit_remote_direct_or_peer_reflexive_checks():
    async def run():
        pc=create_peer([dict(urls=['turn:free.expressturn.com:3478'],username='fixture',credential='fixture')],True)
        pc.createDataChannel('fixture');connection=pc.sctp.transport.transport._connection
        try:
            await connection.add_remote_candidate(candidate('host',1000));await connection.add_remote_candidate(candidate('srflx',1001))
            await connection.add_remote_candidate(candidate('relay',2000))
            assert [c.type for c in connection.remote_candidates]==['relay']
            responses=[];connection.respond_error=lambda *args:responses.append(args)
            request=stun.Message(message_method=stun.Method.BINDING,message_class=stun.Class.REQUEST)
            relay=SimpleNamespace(local_candidate=candidate('relay',3000));host=SimpleNamespace(local_candidate=candidate('host',3001))
            connection.request_received(request,('203.0.113.12',1000),relay,b'invalid-auth')
            connection.request_received(request,('203.0.113.12',2000),host,b'invalid-auth')
            assert responses==[] and len(connection.remote_candidates)==1
            connection.request_received(request,('203.0.113.12',2000),relay,b'invalid-auth')
            assert len(responses)==1
        finally:await pc.close()
    asyncio.run(run())

def test_automatic_mode_keeps_direct_candidates():
    async def run():
        pc=create_peer([],False);pc.createDataChannel('fixture');connection=pc.sctp.transport.transport._connection
        try:
            await connection.add_remote_candidate(candidate('host',1000))
            assert connection.remote_candidates[0].type=='host'
        finally:await pc.close()
    asyncio.run(run())

def test_forced_relay_cannot_fall_back_to_plain_tcp():
    with pytest.raises(ProtocolError,match='TURN público'):peer_client_socket(dict(host='127.0.0.1',port=1),force_relay=True)

@pytest.mark.parametrize('udp_delay,udp_fails',[(.03,False),(.01,True),(2,False)])
def test_udp_preferred_with_bounded_tcp_fallback(monkeypatch,udp_delay,udp_fails):
    import time
    import aioice.ice as ice
    from novoacesso.ice_policy import gather_component
    finished=[]
    async def allocate(**option):
        transport=option['turn_transport']
        try:
            await asyncio.sleep(udp_delay if transport=='udp' else .005)
            if transport=='udp' and udp_fails:raise OSError('blocked UDP')
            c=candidate('relay',2000 if transport=='udp' else 2001)
            return c,SimpleNamespace(local_candidate=c)
        finally:finished.append(transport)
    monkeypatch.setattr(ice,'relayed_candidate',allocate)
    connection=SimpleNamespace(stun_server=None,_protocols=[],_novo_turn_options=[dict(turn_transport='udp'),dict(turn_transport='tcp')])
    started=time.monotonic();values=asyncio.run(gather_component(connection,1,[]))
    assert time.monotonic()-started<1 and sorted(finished)==['tcp','udp']
    if not udp_fails and udp_delay<1:
        assert {v.port for v in values}=={2000,2001}
        assert next(v.priority for v in values if v.port==2000)>next(v.priority for v in values if v.port==2001)
    else:assert [v.port for v in values]==[2001]
