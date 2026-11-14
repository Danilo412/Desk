"""Stable human-readable device identifiers and signed online lookup offers.

The short number is an identifier, not an access credential. A full signing-key
pin is retained only after a successful TLS session; it is never replaced by a
different key returned by the directory. There is no central ID allocator.
"""
from functools import lru_cache
import hashlib,json,secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .wire import ProtocolError,parse_invitation

def normalize_address(value):
    if not isinstance(value,str):raise ProtocolError('Digite o endereço de 12 números.')
    code=''.join(c for c in value if c not in ' -\t\r\n')
    if len(code)!=12 or any(c not in '0123456789' for c in code):raise ProtocolError('Digite os 12 números do endereço Desk.')
    return code

def canonical_public(value):
    if not isinstance(value,str) or len(value)!=64:raise ProtocolError('Identidade do endereço inválida.')
    try:raw=bytes.fromhex(value)
    except ValueError as ex:raise ProtocolError('Identidade do endereço inválida.') from ex
    if len(raw)!=32:raise ProtocolError('Identidade do endereço inválida.')
    return raw.hex()

@lru_cache(maxsize=256)
def address_for_public(public):
    public=canonical_public(public)
    # Freeze this v1 mapping: changing app version must not change an address.
    material=hashlib.scrypt(bytes.fromhex(public),salt=b'Desk fixed address v1',n=16384,r=8,p=1,maxmem=64*1024*1024,dklen=32)
    return f'{int.from_bytes(material,"big") % 10**12:012d}'

def format_address(value):
    code=normalize_address(value)
    return ' '.join(code[i:i+4] for i in (0,4,8))

def offer_bytes(code,token,nonce,public):
    public=canonical_public(public);code=normalize_address(code)
    if not isinstance(nonce,str) or len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce):raise ProtocolError('Desafio do endereço inválido.')
    parse_invitation(token)
    return b'Desk fixed address offer v1\0'+json.dumps(dict(code=code,token=token,nonce=nonce,public=public),sort_keys=True,separators=(',',':')).encode()

def verify_offer(code,token,nonce,public,signature,expected_public=None):
    public=canonical_public(public)
    if not isinstance(signature,str) or len(signature)!=128:raise ProtocolError('Resposta do endereço sem assinatura válida.')
    try:Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(bytes.fromhex(signature),offer_bytes(code,token,nonce,public))
    except Exception as ex:
        # All cryptographic/parser failures reject the offer; no unsigned fallback.
        raise ProtocolError('Resposta do endereço sem assinatura válida.') from ex
    if expected_public is not None and not secrets.compare_digest(public,canonical_public(expected_public)):
        raise ProtocolError('A identidade deste endereço é diferente da conexão anterior.')
    if not secrets.compare_digest(address_for_public(public),normalize_address(code)):
        raise ProtocolError('Este dispositivo não corresponde ao endereço solicitado.')
    return public
