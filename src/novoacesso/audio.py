"""Áudio do sistema por WASAPI loopback; não abre microfone como fallback."""
import queue
import threading
import zlib
from .codec import bounded_inflate
from .wire import ProtocolError
from .audio_backend import audio_thread_context,play_audio
from .audio_codec import CAPABILITY,OpusEncoder,OpusDecoder,AudioPlayout,pcm48,MAGIC

RATE=16000
FRAMES=1600
CHANNELS=2

def capture_loop(peer):
    try:
        import soundcard as sc
        import numpy as np
        with audio_thread_context():
            speaker=sc.default_speaker()
            if speaker is None:raise RuntimeError("Nenhuma saída de áudio encontrada.")
            microphone=sc.get_microphone(speaker.id,include_loopback=True)
            if microphone is None or not microphone.isloopback:raise RuntimeError("Captura do áudio do sistema indisponível.")
            ready=getattr(peer,'capabilities_received',None)
            if ready:ready.wait(.5)
            modern=CAPABILITY in getattr(peer,'remote_media',set())
            rate,frames=(48000,960) if modern else (RATE,FRAMES)
            encoder=OpusEncoder() if modern else None
            peer.audio_format='Opus · estéreo · 48 kHz' if modern else 'Áudio compatível · 16 kHz'
            fast=getattr(peer,'fast_audio',None)
            if modern and fast and fast.prepare_send():peer.audio_format+=' · canal independente'
            with microphone.recorder(samplerate=rate,channels=CHANNELS,blocksize=frames) as recorder:
                while not peer.closed.is_set() and peer.permissions.get("audio",False):
                    samples=recorder.record(numframes=frames)
                    raw=(np.clip(samples,-1,1)*32767).astype("<i2").tobytes()
                    if len(raw)==frames*CHANNELS*2 and not peer.closed.is_set() and peer.permissions.get("audio",False):
                        payload=encoder.encode(samples) if encoder else zlib.compress(raw,1)
                        if not (modern and fast and fast.send(payload)):peer.channel.send(b'A',payload)
    except Exception as ex:
        if not peer.closed.is_set():peer.event("notice",{"text":"Áudio do sistema indisponível: "+str(ex)[:180]})
    finally:peer.audio_capture_running=False

def playback_loop(peer):
    try:
        import soundcard as sc
        import numpy as np
        with audio_thread_context():
            speaker=sc.default_speaker()
            if speaker is None:raise RuntimeError("Nenhuma saída de áudio encontrada.")
            def fresh_playout():
                quality=getattr(peer,'quality',None)
                return AudioPlayout(min(360,max(120,getattr(quality,'rtt_ms',0)+100)))
            playout=fresh_playout()
            with speaker.player(samplerate=48000,channels=CHANNELS,blocksize=2880) as player:
                while not peer.closed.is_set():
                    if not peer.permissions.get('audio',False):
                        playout=fresh_playout()
                        while True:
                            try:peer.audio_queue.get_nowait()
                            except queue.Empty:break
                        peer.closed.wait(.02);continue
                    try:
                        raw=peer.audio_queue.get_nowait() if playout.started else peer.audio_queue.get(timeout=.02)
                        playout.push(pcm48(raw,48000 if len(raw)==960*4 else RATE))
                    except queue.Empty:pass
                    while True:
                        try:
                            raw=peer.audio_queue.get_nowait();playout.push(pcm48(raw,48000 if len(raw)==960*4 else RATE))
                        except queue.Empty:break
                    samples=playout.take()
                    if samples is None:continue
                    peer.audio_metrics=dict(underruns=playout.underruns,discarded_samples=playout.dropped,buffered_ms=round(len(playout.buffer)/48))
                    play_audio(player,samples,peer.closed)
    except Exception as ex:
        if not peer.closed.is_set():peer.event("notice",{"text":"Reprodução de áudio indisponível: "+str(ex)[:180]})
    finally:peer.audio_playback_running=False

def receive_audio(peer,payload):
    if peer.role!="viewer" or not peer.permissions.get("audio",False):return
    rate=RATE
    if payload.startswith(MAGIC):
        if CAPABILITY not in getattr(peer,'remote_media',set()):raise ProtocolError('Áudio de alta qualidade não negociado.')
        if getattr(peer,'opus_decoder',None) is None:peer.opus_decoder=OpusDecoder()
        raw=peer.opus_decoder.decode(payload);rate=48000
    else:raw=bounded_inflate(payload,FRAMES*CHANNELS*2)
    if not raw or len(raw)%(CHANNELS*2):raise ProtocolError('Bloco de áudio inválido.')
    observer=getattr(peer,'recording_audio_sink',None)
    if observer:
        try:observer(raw,rate,CHANNELS)
        except Exception:peer.recording_audio_sink=None
    if not peer.audio_playback_running:
        peer.audio_playback_running=True
        threading.Thread(target=playback_loop,args=(peer,),daemon=True).start()
    # A full playback queue must discard the oldest sound, not retain it and
    # drop new arrivals indefinitely when the output device falls behind.
    while peer.audio_queue.qsize()>=(24 if rate==48000 else 4):
        try:peer.audio_queue.get_nowait()
        except queue.Empty:break
    try:peer.audio_queue.put_nowait(raw)
    except queue.Full:
        try:peer.audio_queue.get_nowait()
        except queue.Empty:pass
        try:peer.audio_queue.put_nowait(raw)
        except queue.Full:pass
