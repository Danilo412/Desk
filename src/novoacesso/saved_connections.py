"""Acessos permanentes protegidos pelo estado DPAPI e senha local opcional."""
import base64,hashlib,secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .unattended import parse_profile
from .quality import preferences
from .device_address import normalize_address

CARD_COLORS=('#35485b','#386357','#784448','#64517a','#75623f')

def _name(value):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>80:raise ValueError('Escolha um nome de até 80 caracteres para este computador.')
    return value.strip()

def _key(password,salt):return hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,maxmem=128*1024*1024,dklen=32)

def save_connection(identity,name,profile,password='',view=None):
    parse_profile(profile)
    name=name.strip()
    if not name or len(name)>80:raise ValueError('Escolha um nome de até 80 caracteres para este computador.')
    if password and not 8<=len(password)<=256:raise ValueError('Use pelo menos 8 caracteres na senha local.')
    id=secrets.token_hex(16);entry={'name':name,'locked':bool(password),'view':preferences(view)}
    if password:
        salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12)
        raw=salt+nonce+AESGCM(_key(password,salt)).encrypt(nonce,profile.encode(),id.encode())
        entry['sealed']=base64.b64encode(raw).decode()
    else:entry['profile']=profile
    with identity.lock:identity.data.setdefault('connections',{})[id]=entry;identity.save()
    return id

def list_connections(identity):
    with identity.lock:
        result=[]
        for id,item in identity.data.get('connections',{}).items():
            entry={'id':id,'name':item['name'],'locked':item['locked'],'view':preferences(item.get('view')),
                   'kind':item.get('kind','authorized'),'color':item.get('color',CARD_COLORS[0])}
            if entry['kind']=='address':entry['address']=normalize_address(item['address'])
            result.append(entry)
        return result

def save_address(identity,name,address,view=None):
    name=_name(name);address=normalize_address(address)
    with identity.lock:
        connections=identity.data.setdefault('connections',{})
        id=next((id for id,item in connections.items() if item.get('kind')=='address' and item.get('address')==address),None) or secrets.token_hex(16)
        item=connections.setdefault(id,{})
        item.update(name=name,kind='address',address=address,locked=False,view=preferences(view))
        identity.save()
    return id

def update_connection(identity,id,name=None,color=None):
    if name is not None:name=_name(name)
    if color is not None and color not in CARD_COLORS:raise ValueError('Escolha uma cor disponível para o cartão.')
    with identity.lock:
        item=identity.data.get('connections',{}).get(id)
        if item is None:raise ValueError('Acesso salvo não encontrado.')
        if name is not None:item['name']=name
        if color is not None:item['color']=color
        identity.save()

def update_preferences(identity,id,value):
    with identity.lock:
        entry=identity.data.get('connections',{}).get(id)
        if entry is not None:entry['view']=preferences(value);identity.save()

def open_connection(identity,id,password=''):
    with identity.lock:entry=dict(identity.data.get('connections',{}).get(id,{}))
    if not entry:raise ValueError('Acesso salvo não encontrado.')
    if entry.get('kind')=='address':return normalize_address(entry['address'])
    if entry['locked']:
        try:
            raw=base64.b64decode(entry['sealed'],validate=True)
            profile=AESGCM(_key(password,raw[:16])).decrypt(raw[16:28],raw[28:],id.encode()).decode()
        except Exception as ex:raise ValueError('Senha local incorreta ou acesso salvo inválido.') from ex
    else:profile=entry['profile']
    parse_profile(profile);return profile

def remove_connection(identity,id):
    with identity.lock:identity.data.get('connections',{}).pop(id,None);identity.save()
