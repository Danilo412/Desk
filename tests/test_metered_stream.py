"""Real SDK + real WebRTC, with local signaling and synthetic payloads."""
import asyncio
import concurrent.futures
import json
import threading
import time
import ssl
from metered_realtime import MeteredPeer
from websockets.asyncio.server import serve
from novoacesso.metered_stream import MeteredStream
from novoacesso.relay import endpoint_from_token
from novoacesso.relay import InnerTLS
from novoacesso.wire import tls_identity,Channel
from novoacesso.relay import validate_endpoint
import pytest


def test_metered_endpoint():
    key='pk_live_'+'a'*32
    assert endpoint_from_token(key)['mode']=='metered'
    endpoint=validate_endpoint({'mode':'metered','api_key':key,'ice_servers':[{'urls':'turns:global.relay.metered.ca:443?transport=tcp','username':'client','credential':'scoped-test-value'}]})
    assert endpoint['ice_servers'][0]['urls']==['turns:global.relay.metered.ca:443?transport=tcp']
    express=validate_endpoint(dict(endpoint,ice_servers=[{'urls':'turn:free.expressturn.com:3478?transport=tcp','username':'client','credential':'scoped-test-value'}]))
    assert express['ice_servers'][0]['urls']==['turn:free.expressturn.com:3478?transport=tcp']
    with pytest.raises(Exception,match='Endereço TURN'):
        validate_endpoint(dict(endpoint,ice_servers=[{'urls':'turn:unrelated.example:443','username':'client','credential':'value'}]))
    with pytest.raises(Exception,match='Endereço TURN'):
        validate_endpoint(dict(endpoint,ice_servers=[{'urls':'turn:free.expressturn.com.attacker.example:3478','username':'client','credential':'value'}]))


def test_real_webrtc_duplex_and_cleanup():
    ready=threading.Event();state={};peers={};rooms={}
    async def handler(ws):
        pid='peer-'+str(len(peers)+1);peers[pid]=ws
        async def send(target,data):await target.send(json.dumps(data))
        await send(ws,dict(type='welcome',peerId=pid,serverTime=int(time.time()*1000),maxMessageSize=65536,metadata={'iceServers':[]}))
        try:
            async for raw in ws:
                msg=json.loads(raw);kind=msg['type']
                if 'requestId' in msg:await send(ws,dict(type='ack',requestId=msg['requestId']))
                if kind=='subscribe':
                    room=msg['channel'];members=rooms.setdefault(room,set())
                    await send(ws,dict(type='presence',channel=room,joined=[{'peerId':p} for p in members],left=[]))
                    for p in list(members):await send(peers[p],dict(type='presence',channel=room,joined=[{'peerId':pid}],left=[]))
                    members.add(pid)
                elif kind=='send' and msg['to'] in peers:await send(peers[msg['to']],dict(type='direct',**{'from':pid},data=msg['data']))
                elif kind=='ping':await send(ws,dict(type='pong'))
        finally:
            peers.pop(pid,None)
            for members in rooms.values():members.discard(pid)
    async def server():
        state['loop']=asyncio.get_running_loop();state['stop']=asyncio.Event()
        async with serve(handler,'127.0.0.1',0) as listener:
            state['port']=listener.sockets[0].getsockname()[1];ready.set();await state['stop'].wait()
    thread=threading.Thread(target=lambda:asyncio.run(server()),daemon=True);thread.start();assert ready.wait(5)
    def factory(**kwargs):return MeteredPeer(url='ws://127.0.0.1:'+str(state['port']),**kwargs)
    streams=[MeteredStream('pk_live_'+'a'*32,'room','route',peer_factory=factory) for _ in range(2)]
    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(stream.open,20) for stream in streams]
            for future in futures:future.result(25)
        a,b=streams;a.settimeout(5);b.settimeout(5)
        a.sendall(b'host-to-viewer');assert b.recv(100)==b'host-to-viewer'
        b.sendall(b'viewer-to-host');assert a.recv(100)==b'viewer-to-host'
        payload=b'bounded reliable transport\0'*80000
        def receive():
            result=bytearray()
            while len(result)<len(payload):
                chunk=b.recv(65536)
                assert chunk
                result.extend(chunk)
            return bytes(result)
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future=pool.submit(receive)
            a.sendall(payload)
            assert future.result(15)==payload
        server_context,_=tls_identity()
        client_context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.check_hostname=False;client_context.verify_mode=ssl.CERT_NONE
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            server_future=pool.submit(InnerTLS,b,server_context,True)
            client_tls=InnerTLS(a,client_context)
            server_tls=server_future.result(10)
        client_channel=Channel(client_tls);server_channel=Channel(server_tls)
        try:
            client_channel.start_io();server_channel.start_io()
            client_channel.send(b'F',payload)
            assert server_channel.receive()==(b'F',payload)
        finally:client_channel.close();server_channel.close()
    finally:
        for stream in streams:stream.close()
        for stream in streams:stream.thread.join(5)
        state['loop'].call_soon_threadsafe(state['stop'].set);thread.join(5)
    assert all(not stream.thread.is_alive() for stream in streams)
