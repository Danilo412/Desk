"""Valida alocação real TURN; o primeiro desafio 401 é tratado por aioice."""
import asyncio
from urllib.parse import urlsplit,parse_qs
from .relay import validate_endpoint

async def allocation(server,transport):
    from aioice import Connection
    from aioice.ice import relayed_candidate,StunProtocol
    url=next((u for u in server['urls'] if u.startswith(('turn:','turns:'))),None)
    if not url:raise ValueError('Servidor TURN ausente.')
    parsed=urlsplit(url.replace('turns:','turns://',1) if url.startswith('turns:') else url.replace('turn:','turn://',1))
    connection=Connection(ice_controlling=True);handler=None
    try:
        candidate,handler=await asyncio.wait_for(relayed_candidate(component=1,protocol_factory=lambda:StunProtocol(connection),turn_server=(parsed.hostname,parsed.port or 3478),turn_username=server['username'],turn_password=server['credential'],turn_ssl=parsed.scheme=='turns',turn_transport=transport),15)
        return dict(passed=candidate.type=='relay',transport=transport)
    except Exception as ex:
        raw=str(ex)
        status='authentication' if '401' in raw or '441' in raw else 'timeout' if isinstance(ex,(asyncio.TimeoutError,TimeoutError)) else 'unavailable'
        messages={'authentication':'O servidor recusou o usuário ou a senha TURN. Copie os campos Username e Password do Dashboard, não o login da conta.',
                  'timeout':'O relay não respondeu no prazo. Verifique a rede e a porta do servidor.',
                  'unavailable':'Não foi possível abrir uma alocação no relay.'}
        return dict(passed=False,transport=transport,category=status,message=messages[status])
    finally:
        if handler:await handler.close()
        await connection.close()

async def validate_config(config):
    endpoint=validate_endpoint(dict(mode='metered',api_key=config['public_key'],ice_servers=config['ice_servers']))
    servers=[s for s in endpoint['ice_servers'] if any(u.startswith(('turn:','turns:')) for u in s['urls'])]
    if not servers:raise ValueError('Configure um servidor TURN com usuário e senha de relay.')
    results=await asyncio.gather(*(allocation(servers[0],protocol) for protocol in ('udp','tcp')))
    return dict(passed=any(r['passed'] for r in results),checks=results)
