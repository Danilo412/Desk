"""One catalog entry per known device; preserve encrypted access and history."""
import copy
from pathlib import Path
import re
import shutil
import time
from .device_address import normalize_address
from .unattended import parse_profile

def address(value):
    try:return normalize_address(value)
    except Exception:return ''

def fingerprint(item):
    value=item.get('peer_fp','')
    if not item.get('locked') and item.get('profile'):
        try:
            actual=parse_profile(item['profile'])['fp']
            if value and value!=actual:return ''
            value=actual
        except Exception:return ''
    return value if isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) else ''

def generic_name(name,number=''):
    text=str(name or '').strip().casefold()
    return text in ('','computador remoto','computador autorizado','pc '+number,number) or address(text)==number and bool(number)

def recent_entries(entries,connections,aliases=None):
    aliases=aliases or {};result=[];seen=set()
    for original in entries:
        if not isinstance(original,dict):continue
        item=dict(original);saved_id=aliases.get(item.get('saved_id'),item.get('saved_id'));saved=connections.get(saved_id,{})
        number=address(item.get('address')) or (address(item.get('label')) if item.get('fixed') else '')
        if not saved and number:
            matches=[(id,e) for id,e in connections.items() if address(e.get('address'))==number]
            if len(matches)==1:saved_id,saved=matches[0]
        fp=item.get('peer_fp') or fingerprint(saved)
        if saved:
            item['saved_id']=saved_id
            number=address(saved.get('address')) or number
        if number:item.update(address=number,label=number,fixed=True)
        if fp:item['peer_fp']=fp
        key=('fp',fp) if fp else ('address',number) if number else ('saved',saved_id) if saved_id else ('unknown',len(result))
        if key in seen:continue
        seen.add(key);result.append(item)
    return result[:20]

def consolidate_connections(identity):
    """Merge only a matching certificate or an unambiguous numeric favorite.

    A locked entry keeps its ID and ciphertext (the ID is its AES-GCM AAD).
    Different authorized certificates are never merged just by name/address.
    """
    with identity.lock:
        old=identity.data.get('connections',{});connections=copy.deepcopy(old);groups={};by_address={}
        for id,item in connections.items():
            fp=fingerprint(item);number=address(item.get('address'))
            key=('fp',fp) if fp else ('address',number) if item.get('kind')=='address' and number else ('id',id)
            groups.setdefault(key,[]).append(id)
            if fp and number:by_address.setdefault(number,set()).add(key)
        for key in list(groups):
            if key[0]=='address' and len(by_address.get(key[1],()))==1:
                target=next(iter(by_address[key[1]]));groups[target].extend(groups.pop(key))
        aliases={};merged={}
        for key,ids in groups.items():
            def score(id):
                item=connections[id]
                return (bool(item.get('locked')),item.get('kind','authorized')=='authorized',not generic_name(item.get('name'),address(item.get('address'))))
            winner=max(ids,key=score);item=connections[winner]
            numbers={address(connections[id].get('address')) for id in ids}-{''}
            if len(numbers)==1:item['address']=next(iter(numbers))
            if generic_name(item.get('name'),address(item.get('address'))):
                custom=next((connections[id]['name'] for id in ids if not generic_name(connections[id].get('name'),address(connections[id].get('address')))),None)
                if custom:item['name']=custom
            if not item.get('color'):
                color=next((connections[id].get('color') for id in ids if connections[id].get('color')),None)
                if color:item['color']=color
            if key[0]=='fp':
                item['peer_fp']=key[1]
                if not item.get('locked'):
                    profiles=[connections[id]['profile'] for id in ids if not connections[id].get('locked') and connections[id].get('profile') and fingerprint(connections[id])==key[1]]
                    if profiles:item['profile']=profiles[-1]
            merged[winner]=item
            for id in ids:
                if id!=winner:aliases[id]=winner
        settings=identity.data.setdefault('settings',{});old_recent=settings.get('desk_recents',[])
        recents=recent_entries(old_recent,merged,aliases)
        if merged!=old or recents!=old_recent:
            path=getattr(identity,'path',None)
            if path and Path(path).exists():
                backup=Path(path).parent/'backups';backup.mkdir(exist_ok=True)
                shutil.copy2(path,backup/f'connections-before-merge-{time.time_ns()}.dat')
            identity.data['connections']=merged
            if recents!=old_recent:settings['desk_recents']=recents
            identity.save()
        return aliases

def remember_recent(identity,entry):
    with identity.lock:
        entries=recent_entries([entry,*identity.settings().get('desk_recents',[])],identity.data.get('connections',{}))
        identity.configure(desk_recents=entries)
        return entries
