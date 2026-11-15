"""Áudio do sistema por WASAPI loopback; não abre microfone como fallback."""
import queue
import threading
import zlib
from .codec import bounded_inflate
from .wire import ProtocolError
from .audio_backend import audio_thread_context,play_audio

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
            with microphone.recorder(samplerate=RATE,channels=CHANNELS,blocksize=FRAMES) as recorder:
                while not peer.closed.is_set() and peer.permissions.get("audio",False):
                    samples=recorder.record(numframes=FRAMES)
                    raw=(np.clip(samples,-1,1)*32767).astype("<i2").tobytes()
                    if len(raw)==FRAMES*CHANNELS*2 and not peer.closed.is_set() and peer.permissions.get("audio",False):
                        peer.channel.send(b"A",zlib.compress(raw,1))
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
            with speaker.player(samplerate=RATE,channels=CHANNELS,blocksize=FRAMES) as player:
                while not peer.closed.is_set():
                    try:raw=peer.audio_queue.get(timeout=.5)
                    except queue.Empty:continue
                    if not peer.permissions.get('audio',False):continue
                    samples=np.frombuffer(raw,dtype="<i2").reshape(-1,CHANNELS).astype(np.float32)/32768
                    play_audio(player,samples,peer.closed)
    except Exception as ex:
        if not peer.closed.is_set():peer.event("notice",{"text":"Reprodução de áudio indisponível: "+str(ex)[:180]})
    finally:peer.audio_playback_running=False

def receive_audio(peer,payload):
    if peer.role!="viewer" or not peer.permissions.get("audio",False):return
    raw=bounded_inflate(payload,FRAMES*CHANNELS*2)
    if not raw or len(raw)%(CHANNELS*2):raise ProtocolError('Bloco de áudio inválido.')
    observer=getattr(peer,'recording_audio_sink',None)
    if observer:
        try:observer(raw,RATE,CHANNELS)
        except Exception:peer.recording_audio_sink=None
    if not peer.audio_playback_running:
        peer.audio_playback_running=True
        threading.Thread(target=playback_loop,args=(peer,),daemon=True).start()
    # A full playback queue must discard the oldest sound, not retain it and
    # drop new arrivals indefinitely when the output device falls behind.
    try:peer.audio_queue.put_nowait(raw)
    except queue.Full:
        try:peer.audio_queue.get_nowait()
        except queue.Empty:pass
        try:peer.audio_queue.put_nowait(raw)
        except queue.Full:pass
