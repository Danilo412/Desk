"""Identidade e autorizações locais. Chaves privadas protegidas com DPAPI no Windows."""
from __future__ import annotations
import base64,ctypes,datetime,hashlib,json,os,secrets,ssl,tempfile,threading
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec,ed25519
from cryptography.x509.oid import NameOID

def protect(data,encrypt=True):
    if os.name!='nt':return data  # Arquivo 0600 em pasta 0700, para o servidor Linux.
    class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));dest=Blob()
    api=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=api.CryptProtectData if encrypt else api.CryptUnprotectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
    fn.restype=ctypes.c_int;kernel.LocalFree.argtypes=[ctypes.c_void_p]
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(dest)):raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(dest.data,dest.size)
    finally:kernel.LocalFree(dest.data)

class IdentityStore:
    def __init__(self,root=None):
        self.root=Path(root or os.environ.get('NOVOACESSO_STATE_DIR') or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'NovoAcesso')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.path=self.root/'identity.dat';self.lock=threading.RLock()
        if self.path.exists():self.data=json.loads(protect(self.path.read_bytes(),False))
        else:
            key=ec.generate_private_key(ec.SECP256R1());now=datetime.datetime.now(datetime.timezone.utc)
            subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Novo Acesso próprio')])
            cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1825)).sign(key,hashes.SHA256()))
            self.data=dict(sign=ed25519.Ed25519PrivateKey.generate().private_bytes_raw().hex(),
                tls=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),
                cert=cert.public_bytes(serialization.Encoding.PEM).decode(),trusted={},settings={},route=secrets.token_urlsafe(32))
            self.save()
        from .password_access import PasswordAccess
        self.password_access=PasswordAccess(self)
    def save(self):
        with self.lock:
            raw=protect(json.dumps(self.data,ensure_ascii=False).encode())
            with tempfile.NamedTemporaryFile(dir=self.root,delete=False) as out:out.write(raw);tmp=Path(out.name)
            try:tmp.chmod(0o600);tmp.replace(self.path)
            finally:tmp.unlink(missing_ok=True)
    @property
    def public(self):return self.signing_key.public_key().public_bytes_raw().hex()
    @property
    def signing_key(self):return ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.data['sign']))
    @property
    def device_id(self):return hashlib.sha256(bytes.fromhex(self.public)).hexdigest()
    @property
    def desk_address(self):
        from .device_address import address_for_public
        return address_for_public(self.public)
    @property
    def certificate_fingerprint(self):
        return x509.load_pem_x509_certificate(self.data['cert'].encode()).fingerprint(hashes.SHA256()).hex()
    def address_peer(self,code):
        from .device_address import normalize_address
        code=normalize_address(code)
        with self.lock:return self.data.get('desk_peers',{}).get(code)
    def pin_address(self,code,public):
        from .device_address import normalize_address,canonical_public,address_for_public
        from .wire import ProtocolError
        code=normalize_address(code);public=canonical_public(public)
        if address_for_public(public)!=code:raise ProtocolError('Identidade incompatível com o endereço Desk.')
        with self.lock:
            old=self.data.get('desk_peers',{}).get(code)
            if old is not None and not secrets.compare_digest(old,public):raise ProtocolError('A identidade deste endereço mudou; a conexão foi interrompida.')
            if old is None:self.data.setdefault('desk_peers',{})[code]=public;self.save()
    def tls_identity(self):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_3
        with tempfile.TemporaryDirectory(prefix='novoacesso-cert-') as tmp:
            cert=Path(tmp)/'cert.pem';key=Path(tmp)/'key.pem';cert.write_text(self.data['cert']);key.write_text(self.data['tls'])
            context.load_cert_chain(cert,key)
        cert=x509.load_pem_x509_certificate(self.data['cert'].encode())
        return context,hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    def trust(self,public,label):
        if not isinstance(public,str) or len(bytes.fromhex(public))!=32:raise ValueError('Identidade do dispositivo inválida.')
        with self.lock:self.data['trusted'][public]={'name':str(label)[:80]};self.save()
    def revoke(self,public):
        with self.lock:self.data['trusted'].pop(public,None);self.save()
    def trusted(self,public):
        with self.lock:return public in self.data['trusted']
    def settings(self):
        with self.lock:return dict(self.data['settings'])
    def configure(self,**values):
        with self.lock:self.data['settings'].update(values);self.save()

def challenge_bytes(nonce,fp):return b'NovoAcesso unattended v1\x00'+bytes.fromhex(nonce)+bytes.fromhex(fp)

def verify_proof(public,signature,nonce,fp):
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(bytes.fromhex(signature),challenge_bytes(nonce,fp))
        return True
    except Exception:return False
