"""Fábrica ICE e modo estrito para comprovar tráfego pelo TURN configurado."""
from aiortc import RTCConfiguration,RTCIceServer,RTCPeerConnection
import asyncio,ipaddress,socket

async def gather_component(connection,component,addresses,timeout=5):
    # Construção dos candidatos compatível com aioice 0.10.2 (BSD-3-Clause;
    # licença incluída). A espera termina quando STUN e TURN já responderam,
    # sem esperar esgotar interfaces secundárias que não alcançam a internet.
    import aioice.ice as ice
    from aioice import turn
    candidates=[];hosts=[];queries={};pending=set()
    loop=asyncio.get_running_loop();stun_ready=connection.stun_server is None;turn_success=False;udp_success=False
    for address in addresses:
        try:
            transport,protocol=await loop.create_datagram_endpoint(lambda:ice.StunProtocol(connection),local_addr=(address,0))
            sock=transport.get_extra_info('socket')
            if sock is not None:sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,turn.UDP_SOCKET_BUFFER_SIZE)
        except OSError:continue
        host,port=protocol.transport.get_extra_info('sockname')[:2]
        protocol.local_candidate=ice.Candidate(foundation=ice.candidate_foundation('host','udp',host),component=component,transport='udp',priority=ice.candidate_priority(component,'host'),host=host,port=port,type='host')
        hosts.append(protocol);candidates.append(protocol.local_candidate);connection._protocols.append(protocol)
    if connection.stun_server:
        for protocol in hosts:
            if ipaddress.ip_address(protocol.local_candidate.host).version==4:
                queries[asyncio.create_task(ice.server_reflexive_candidate(protocol,connection.stun_server))]=('stun',None)
    options=getattr(connection,'_novo_turn_options',None)
    if options is None:
        options=[dict(turn_server=connection.turn_server,turn_username=connection.turn_username,turn_password=connection.turn_password,turn_ssl=connection.turn_ssl,turn_transport=connection.turn_transport)] if connection.turn_server else []
    for option in options:
        task=asyncio.create_task(ice.relayed_candidate(component=component,protocol_factory=lambda:ice.StunProtocol(connection),**option));queries[task]=('turn',option.get('turn_transport','udp'))
    pending=set(queries);deadline=loop.time()+timeout
    try:
        while pending and loop.time()<deadline:
            done,pending=await asyncio.wait(pending,timeout=max(0,deadline-loop.time()),return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.cancelled() or task.exception() is not None:continue
                candidate,protocol=task.result()
                if queries[task]==('turn','tcp'):candidate.priority-=1
                candidates.append(candidate)
                if protocol is not None:connection._protocols.append(protocol)
                if candidate.type=='srflx':stun_ready=True
                if candidate.type=='relay':
                    turn_success=True
                    if queries[task]==('turn','udp'):udp_success=True
            udp_pending=any(queries[task]==('turn','udp') for task in pending)
            # Um TCP que respondeu primeiro não deve cancelar imediatamente
            # a alocação UDP. A preferência custa no máximo 250 ms extras.
            if turn_success and not udp_success and udp_pending:deadline=min(deadline,loop.time()+.25)
            turn_done=(turn_success and (udp_success or not udp_pending)) or not any(queries[task][0]=='turn' for task in pending)
            if stun_ready and turn_done:break
    finally:
        for task in pending:task.cancel()
        if pending:await asyncio.gather(*pending,return_exceptions=True)
        for task in pending:
            if not task.cancelled() and task.exception() is None:
                # Uma alocação pode terminar entre FIRST_COMPLETED e cancel().
                # Incorporá-la evita vazar o transporte ou inserir EOF na fila
                # compartilhada ao fechar um protocolo que acabou de nascer.
                candidate,protocol=task.result()
                candidates.append(candidate)
                if protocol is not None and protocol not in connection._protocols:connection._protocols.append(protocol)
    return candidates

class ResponsivePeerConnection(RTCPeerConnection):
    def _RTCPeerConnection__createDtlsTransport(self):
        dtls=super()._RTCPeerConnection__createDtlsTransport()
        connection=dtls.transport._connection
        connection._novo_turn_options=getattr(self,'_novo_turn_options',None)
        async def gather(*args,**kwargs):return await gather_component(connection,*args,**kwargs)
        connection.get_component_candidates=gather
        return dtls

class RelayOnlyPeerConnection(ResponsivePeerConnection):
    # aiortc 1.15 não expõe iceTransportPolicy em RTCConfiguration. Este
    # adaptador restrito ao diagnóstico remove protocolos/candidatos diretos
    # antes da sinalização. Falhar não pode fazer o teste voltar à rota local.
    def _RTCPeerConnection__createDtlsTransport(self):
        dtls=super()._RTCPeerConnection__createDtlsTransport()
        connection=dtls.transport._connection
        original=connection.get_component_candidates
        original_add=connection.add_remote_candidate;original_request=connection.request_received
        async def add_remote(candidate):
            if candidate is not None and candidate.type!='relay':return
            await original_add(candidate)
        def request_received(message,addr,protocol,raw_data):
            # A normal peer may still advertise host candidates and initiate
            # peer-reflexive checks. Accept only its advertised TURN endpoint,
            # before sending a STUN response or learning a new direct pair.
            if protocol.local_candidate.type!='relay':return
            if not any(c.type=='relay' and c.host==addr[0] and c.port==addr[1] for c in connection.remote_candidates):return
            return original_request(message,addr,protocol,raw_data)
        connection.add_remote_candidate=add_remote;connection.request_received=request_received
        retired=[];original_close=connection.close
        async def close():
            try:await original_close()
            finally:
                for protocol in retired:await protocol.close()
                retired.clear()
        connection.close=close
        async def relay_candidates(*args,**kwargs):
            candidates=await original(*args,**kwargs)
            removed=[p for p in connection._protocols if p.local_candidate.type!='relay']
            connection._protocols=[p for p in connection._protocols if p.local_candidate.type=='relay']
            # Fechar um StunProtocol insere EOF na fila compartilhada do ICE.
            # Retirá-lo da lista de pares já impede a rota direta; fechá-lo
            # somente no encerramento preserva o transporte TURN que continua.
            retired.extend(removed)
            relays=[c for c in candidates if c.type=='relay']
            if not relays:raise ConnectionError('O TURN não forneceu uma rota de retransmissão. Confira as credenciais do relay.')
            return relays
        connection.get_component_candidates=relay_candidates
        return dtls

def create_peer(servers,relay_only=False):
    # aiortc seleciona apenas um TURN. Preservar a ordem da configuração
    # permite priorizar o transporte que passou no teste de alocação.
    ice=[RTCIceServer(urls=url,username=item.get('username'),credential=item.get('credential')) for item in servers for url in item['urls']]
    pc=(RelayOnlyPeerConnection if relay_only else ResponsivePeerConnection)(configuration=RTCConfiguration(iceServers=ice))
    from aiortc.rtcicetransport import connection_kwargs
    options=[];seen=set()
    for server in ice:
        option=connection_kwargs([server])
        if 'turn_server' not in option:continue
        option={k:v for k,v in option.items() if k.startswith('turn_')}
        identity=(option['turn_server'],option.get('turn_transport'),option.get('turn_ssl'))
        if identity not in seen:options.append(option);seen.add(identity)
        if len(options)>=4:break
    pc._novo_turn_options=options
    return pc
