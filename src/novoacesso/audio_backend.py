"""Exact-length writes for the pinned SoundCard 0.4.6 WASAPI backend.

WASAPI may provide a buffer larger than the requested block. Never release
frames that have not been filled: SoundCard's public play() does so for a
partial write. Keep this adapter local to Desk rather than patching SoundCard.
"""
import os
import time
from contextlib import contextmanager


@contextmanager
def audio_thread_context():
    """Balance COM on every audio worker, including workers after reconnect.

    Import SoundCard before entering this context: its initial import also
    initializes COM and its pinned implementation does not accept S_FALSE.
    """
    if os.name != 'nt':
        yield
        return
    import ctypes
    ole32=ctypes.WinDLL('ole32')
    ole32.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    ole32.CoInitializeEx.restype=ctypes.c_long
    hr=ole32.CoInitializeEx(None,0)
    initialized=hr in (0,1)  # S_OK / S_FALSE both require CoUninitialize.
    if not initialized and (hr & 0xffffffff)!=0x80010106:
        raise RuntimeError('Não foi possível iniciar o áudio do Windows (0x%08X).'%(hr & 0xffffffff))
    try:yield
    finally:
        if initialized:ole32.CoUninitialize()


def write_wasapi(player,samples,ffi,closed=None):
    """Fill and release precisely the same number of stereo float32 frames."""
    import numpy as np
    data=np.asarray(samples,dtype=np.float32)
    if data.ndim!=2 or data.shape[1]!=2:
        raise ValueError('O áudio deve conter dois canais.')
    channelmap=player.channelmap
    if len(channelmap)!=2 or set(channelmap)!={0,1}:
        raise RuntimeError('Mapeamento estéreo do dispositivo não suportado.')
    order=sorted(range(2),key=lambda k:channelmap[k])
    data=np.ascontiguousarray(data[:,order])
    position=0
    while position<len(data):
        if closed is not None and closed.is_set():return
        available=player._render_available_frames()
        if available<=0:
            if closed is not None:closed.wait(.001)
            else:time.sleep(.001)
            continue
        count=min(available,len(data)-position)
        chunk=data[position:position+count].tobytes()
        buffer=player._render_buffer(count)
        ffi.memmove(buffer[0],chunk,len(chunk))
        player._render_release(count)
        position+=count


def play_audio(player,samples,closed=None):
    if os.name=='nt':
        from soundcard.mediafoundation import _ffi
        write_wasapi(player,samples,_ffi,closed)
    else:player.play(samples)
