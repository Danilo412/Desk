import os,threading,queue
from types import SimpleNamespace
from novoacesso.audio_transport import AudioCipher,FastAudio,CAPABILITY

def test_audio_datagrams_authenticate_and_reject_replay_and_wrong_session():
    key=os.urandom(32);prefix=os.urandom(4);sender=AudioCipher(key,prefix);receiver=AudioCipher(key,prefix)
    one=sender.seal(b'first');two=sender.seal(b'second')
    assert one[:8]!=two[:8] and receiver.open(one)==b'first' and receiver.open(one) is None
    forged=bytearray(two);forged[-1]^=1
    assert receiver.open(bytes(forged)) is None and receiver.open(two)==b'second'
    assert AudioCipher(os.urandom(32),prefix).open(sender.seal(b'private')) is None
    assert AudioCipher(key,os.urandom(4)).open(sender.seal(b'private')) is None
    assert receiver.open(b'bad') is None

def test_audio_route_requires_negotiation_and_existing_audio_permission():
    outer=SimpleNamespace(datagram_handler=None);sent=[]
    peer=SimpleNamespace(channel=SimpleNamespace(sock=SimpleNamespace(outer=outer)),role='viewer',permissions={'audio':False},remote_media={CAPABILITY},closed=threading.Event(),send=sent.append,spawn=lambda fn:None)
    fast=FastAudio(peer);message=dict(type='audio_route',key=os.urandom(32).hex(),prefix=os.urandom(4).hex())
    fast.handle(message);assert fast.receiver is None and not sent and outer.datagram_handler is None
    peer.permissions['audio']=True;peer.remote_media=set();fast.handle(message);assert fast.receiver is None
    peer.remote_media={CAPABILITY};fast.handle(message)
    assert fast.receiver and callable(outer.datagram_handler) and sent==[dict(type='audio_route_ready')]
    fast.stop();assert fast.receiver is None and outer.datagram_handler is None

def test_audio_route_unavailable_keeps_the_legacy_tls_path():
    peer=SimpleNamespace(channel=SimpleNamespace(sock=object()),remote_media={CAPABILITY},closed=threading.Event())
    assert not FastAudio(peer).prepare_send()
