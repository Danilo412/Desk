import concurrent.futures
import socket
import ssl
from novoacesso.relay import InnerTLS
from novoacesso.wire import tls_identity

class Outer:
    """Byte stream with no decrypted OS-level pending() support, like WebRTC."""
    def __init__(self,sock):self.sock=sock
    def pending(self):return 0
    def __getattr__(self,name):return getattr(self.sock,name)

def tls_pair():
    a,b=socket.socketpair();a.settimeout(3);b.settimeout(3)
    context,_=tls_identity();client=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client.check_hostname=False;client.verify_mode=ssl.CERT_NONE;client.minimum_version=ssl.TLSVersion.TLSv1_3
    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            future=pool.submit(InnerTLS,Outer(b),context,True)
            sender=InnerTLS(Outer(a),client);receiver=future.result(4)
        return sender,receiver
    except BaseException:a.close();b.close();raise

def test_pending_exposes_ciphertext_records_already_read_from_outer_stream():
    sender,receiver=tls_pair()
    try:
        payload=b'0123456789abcdef'*3000
        sender.sendall(payload)
        first=receiver.recv(16384)
        assert first==payload[:16384]
        # One recv read multiple TLS records, while SSLObject.pending only
        # describes the first decrypted record. No next network packet follows.
        assert receiver.inbio.pending>0 and receiver.inner.pending()==0
        assert receiver.pending()>0
        result=first
        receiver.setblocking(False)
        while len(result)<len(payload):result+=receiver.recv(65536)
        assert result==payload
    finally:sender.close();receiver.close()
