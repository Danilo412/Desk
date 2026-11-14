"""Atualiza somente transporte ExpressTURN da mesma conta de sinalização."""
from urllib.parse import urlsplit
from .relay import endpoint_from_token,token_encode,validate_endpoint

def is_express(endpoint):
    urls=[u for s in endpoint.get('ice_servers',[]) for u in s['urls']]
    return bool(urls) and all((urlsplit(u.replace(':', '://',1)).hostname or '').endswith('.expressturn.com') for u in urls)

def use_shipped_relay(previous,cloud,settings):
    old=endpoint_from_token(previous)
    if old.get('mode')!='metered' or old.get('api_key')!=cloud.get('public_key'):return False
    urls=[u for s in old.get('ice_servers',[]) for u in s['urls']]
    if not urls or all('.metered.ca:' in u for u in urls):return True
    return bool(is_express(old) and cloud.get('relay_validated_at') and cloud.get('config_revision') and settings.get('shipped_relay_revision')!=cloud['config_revision'] and not settings.get('relay_customized',False))

def refresh_profile(token,current):
    if not current or current.get('mode')!='metered' or not is_express(current):return token
    if token.startswith('NAU1-'):
        from .unattended import parse_profile
        data=parse_profile(token);prefix='NAU1-'
    elif token.startswith('NA1-'):
        from .wire import parse_invitation
        data=parse_invitation(token);prefix='NA1-'
    else:return token
    old=data.get('relay')
    if not old:return token
    old_endpoint=validate_endpoint(old)
    old_urls=[u for s in old_endpoint.get('ice_servers',[]) for u in s['urls']]
    known_provider=is_express(old_endpoint) or bool(old_urls and all('.metered.ca:' in u for u in old_urls))
    if old_endpoint.get('mode')!='metered' or old_endpoint.get('api_key')!=current.get('api_key') or not known_provider:return token
    data=dict(data,relay=dict(old,ice_servers=current['ice_servers']))
    return token_encode(prefix,data)
