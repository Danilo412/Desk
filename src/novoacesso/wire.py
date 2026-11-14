"""NA/1: TLS 1.3, certificado fixado pelo convite e registros BE32.

Não é uma implementação do protocolo AnyDesk. O segredo só é enviado depois
da conferência do certificado. Cada convite é temporário e de uso único.
"""
from __future__ import annotations
import base64
import datetime
import hashlib
import json
import queue
import select
import secrets
import socket
import ssl
import struct
import tempfile
import threading
import time
from pathlib import Path

MAX_RECORD = 16 * 1024 * 1024
MAX_CONTROL = 64 * 1024

class ProtocolError(Exception):
    pass

class AuthorizationError(ProtocolError,ConnectionError):
    """Recusa definitiva: mantém compatibilidade com falha de conexão."""
    pass

def tls_identity():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Novo Acesso temporário")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(minutes=5))
            .not_valid_after(now+datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    with tempfile.TemporaryDirectory(prefix="novoacesso-cert-") as tmp:
        cert_path, key_path = Path(tmp)/"cert.pem", Path(tmp)/"key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        context.load_cert_chain(cert_path, key_path)
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return context, fingerprint

def make_invitation(host: str, port: int, fingerprint: str, lifetime=600,relay=None):
    data = dict(v=1, host=host, port=port, fp=fingerprint,
                secret=secrets.token_urlsafe(32), expires=int(time.time())+lifetime)
    if relay:data['relay']=relay
    return data, "NA1-"+base64.urlsafe_b64encode(json.dumps(data,separators=(",",":")).encode()).decode().rstrip("=")

def parse_invitation(token: str):
    token = token.strip()
    if not token.startswith("NA1-") or len(token)>4096:
        raise ProtocolError("Convite inválido. Copie o convite completo do outro computador.")
    try:
        raw = token[4:]
        data = json.loads(base64.b64decode(raw+"="*(-len(raw)%4),altchars=b"-_",validate=True))
        assert isinstance(data,dict) and data["v"]==1
        assert isinstance(data["host"],str) and 0<len(data["host"])<=253
        assert not any(c.isspace() for c in data["host"])
        assert type(data["port"]) is int and 1<=data["port"]<=65535
        assert isinstance(data["fp"],str) and len(bytes.fromhex(data["fp"]))==32
        assert isinstance(data["secret"],str) and 32<=len(data["secret"])<=128
        assert type(data["expires"]) is int and data["expires"]>time.time()
    except (ValueError,KeyError,TypeError,AssertionError) as ex:
        raise ProtocolError("Convite inválido ou expirado. Gere um novo convite.") from ex
    return data

class Channel:
    def __init__(self, sock):
        self.sock=sock
        self.sock.settimeout(15)
        self.send_lock=threading.Lock()
        self.closed=threading.Event()
        self.io_thread=None;self.incoming=queue.Queue(maxsize=8);self.outgoing=queue.Queue(maxsize=8);self.failure="Conexão encerrada."
        self.version=1
        self.handshake_mode=False;self.handshake_outgoing=queue.Queue(maxsize=1);self.welcome_queued=False

    def start_io(self,handshake=False):
        """Depois do handshake, apenas esta thread toca o objeto SSL.

        OpenSSL não permite SSL_read/SSL_write simultâneos no mesmo SSL*. Os
        produtores usam filas limitadas; fechar uma sessão sinaliza a thread.
        """
        if self.io_thread is not None:return
        self.handshake_mode=handshake
        if self.version>=2:
            from .multiplex import Outgoing,Incoming
            self.outgoing=Outgoing();self.mux_in=Incoming(MAX_RECORD,MAX_CONTROL,ProtocolError)
        self.sock.setblocking(False)
        self.io_thread=threading.Thread(target=self._pump,daemon=True)
        self.io_thread.start()

    def _pump(self):
        buffer=bytearray();pending=b"";pending_welcome=False
        try:
            while not self.closed.is_set():
                if not pending:
                    if self.handshake_mode:
                        try:pending=self.handshake_outgoing.get_nowait();pending_welcome=True
                        except queue.Empty:pass
                    else:
                        try:pending=self.outgoing.get_nowait()
                        except queue.Empty:pass
                while len(buffer)>=5 and not self.incoming.full():
                    if self.handshake_mode:raise ProtocolError('Dados recebidos antes da aprovação da sessão.')
                    kind=bytes(buffer[:1]);length=struct.unpack_from(">I",buffer,1)[0]
                    self._validate(kind,length)
                    if len(buffer)<5+length:break
                    payload=bytes(buffer[5:5+length]);del buffer[:5+length]
                    if kind==b'M':
                        if self.version<2:raise ProtocolError('Canal não negociado.')
                        result=self.mux_in.feed(payload)
                        if result is not None:self.incoming.put_nowait(result)
                    else:self.incoming.put_nowait((kind,payload))
                can_read=not self.incoming.full()
                if not can_read and not pending:
                    # The decoder can temporarily fill the bounded receive
                    # queue during an HD keyframe. Windows select([], [], [])
                    # raises WSAEINVAL (10022), so wait for consumer capacity
                    # without treating normal backpressure as a disconnect.
                    self.closed.wait(.01);continue
                ready_read,ready_write,_=select.select([self.sock] if can_read else [],[self.sock] if pending else [],[],.01)
                if pending and ready_write:
                    try:
                        written=self.sock.send(pending)
                        if not written:raise ConnectionError("Conexão encerrada.")
                        pending=pending[written:]
                        if not pending and pending_welcome:
                            # Release multiplexed data only after the complete raw
                            # welcome record, preserving old and new clients.
                            self.handshake_mode=False;pending_welcome=False
                    except (ssl.SSLWantReadError,ssl.SSLWantWriteError):pass
                if can_read and (ready_read or self.sock.pending()):
                    try:
                        chunk=self.sock.recv(65536)
                        if not chunk:raise ConnectionError("O outro computador desconectou.")
                        buffer.extend(chunk)
                        if len(buffer)>MAX_RECORD+65541:raise ProtocolError("Buffer recebido fora dos limites.")
                    except (ssl.SSLWantReadError,ssl.SSLWantWriteError):pass
        except Exception as ex:self.failure=str(ex)[:220]
        finally:
            self.closed.set()
            if hasattr(self.outgoing,'close'):self.outgoing.close()
            try:self.sock.close()
            except OSError:pass

    @staticmethod
    def _validate(kind,length):
        if kind not in (b"J",b"V",b"W",b"F",b"A",b'M') or length>MAX_RECORD or (kind==b"J" and length>MAX_CONTROL) or (kind==b'M' and length>16402):
            raise ProtocolError("Registro recebido fora dos limites.")

    def send(self,kind:bytes,payload:bytes):
        if self.closed.is_set():raise ConnectionError("Sessão encerrada.")
        if kind not in (b"J",b"V",b"W",b"F",b"A") or len(payload)>MAX_RECORD:
            raise ProtocolError("Registro fora dos limites.")
        record=kind+struct.pack(">I",len(payload))+payload
        if self.io_thread is not None:
            try:self.outgoing.put(record,timeout=20 if kind==b'F' else 2)
            except queue.Full:raise ConnectionError("A conexão não acompanhou o envio dos dados.")
        else:
            with self.send_lock:self.sock.sendall(record)

    def control(self, data):
        payload=json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
        if len(payload)>MAX_CONTROL:raise ProtocolError("Mensagem muito grande.")
        self.send(b"J",payload)

    def accept_handshake(self,data):
        """Queue the single raw welcome while the pump watches for withdrawal."""
        if self.closed.is_set():raise ConnectionError('A solicitação já foi encerrada.')
        if not self.handshake_mode or self.welcome_queued or data.get('type')!='welcome':raise ProtocolError('Resposta de aprovação inválida.')
        payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if len(payload)>MAX_CONTROL:raise ProtocolError('Mensagem muito grande.')
        self.welcome_queued=True;self.handshake_outgoing.put(b'J'+struct.pack('>I',len(payload))+payload,timeout=2)

    def _read(self,length):
        data=bytearray()
        deadline=time.monotonic()+20
        while len(data)<length:
            if self.closed.is_set():raise ConnectionError("Sessão encerrada.")
            if time.monotonic()>deadline:raise TimeoutError("Tempo limite da mensagem.")
            chunk=self.sock.recv(length-len(data))
            if not chunk:raise ConnectionError("O outro computador desconectou.")
            data.extend(chunk)
        return bytes(data)

    def receive(self):
        if self.io_thread is not None:
            while True:
                if self.closed.is_set():raise ConnectionError(self.failure)
                try:kind,payload=self.incoming.get(timeout=.25);break
                except queue.Empty:continue
        else:
            head=self._read(5)
            kind=head[:1];length=struct.unpack(">I",head[1:])[0]
            self._validate(kind,length)
            payload=self._read(length)
        if kind==b"J":
            try:
                payload=json.loads(payload)
                if not isinstance(payload,dict) or not isinstance(payload.get("type"),str):raise ValueError()
            except (ValueError,UnicodeError) as ex:raise ProtocolError("Mensagem inválida.") from ex
        return kind,payload

    def close(self):
        self.closed.set()
        if hasattr(self.outgoing,'close'):self.outgoing.close()
        if self.io_thread is None:
            try:
                if isinstance(self.sock,socket.socket):socket.socket.shutdown(self.sock,socket.SHUT_RDWR)
                else:self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.sock.close()

def connect_invitation(token,timeout=12):
    data=parse_invitation(token)
    from .relay import peer_client_socket
    return Channel(peer_client_socket(data)),data
