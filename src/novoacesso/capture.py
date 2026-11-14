"""Desktop Duplication opcional, com seleção segura e fallback MSS."""
import os
from PIL import Image
import mss

class CaptureSource:
    def __init__(self):self.screen=None;self.camera=None;self.cached=None;self.dxgi_failed=False;self.unchanged=False;self.backend='MSS';self._com=None
    def __enter__(self):self.screen=mss.MSS();return self
    @property
    def monitors(self):return self.screen.monitors
    def image(self,index):
        monitors=self.monitors;rect=monitors[index];self.unchanged=False
        # A captura acelerada só é usada quando a seleção é inequívoca.
        # Sistemas com múltiplas telas continuam usando o monitor exato do MSS.
        if os.name=='nt' and len(monitors)==2 and index in (0,1) and not self.dxgi_failed and os.environ.get('NOVOACESSO_CAPTURE','auto')!='mss':
            try:
                if self.camera is None:
                    import comtypes
                    comtypes.CoInitialize();self._com=comtypes
                    import dxcam
                    self.camera=dxcam.create(output_idx=None,output_color='BGRA',backend='dxgi',processor_backend='numpy',max_buffer_len=2)
                frame=self.camera.grab()
                if frame is not None:
                    height,width=frame.shape[:2]
                    if (width,height)!=(rect['width'],rect['height']):raise ValueError('Resolução da saída DXGI não corresponde à tela selecionada.')
                    self.cached=Image.frombytes('RGB',(width,height),frame.tobytes(),'raw','BGRX');self.backend='DXGI'
                    return self.cached
                if self.cached is not None:
                    self.unchanged=True;return self.cached
            except Exception:
                self.dxgi_failed=True;self._release_camera()
        shot=self.screen.grab(rect);self.backend='MSS'
        return Image.frombytes('RGB',shot.size,shot.bgra,'raw','BGRX')
    def _release_camera(self):
        if self.camera:
            try:self.camera.release()
            except Exception:pass
            self.camera=None
        if self._com:
            self._com.CoUninitialize();self._com=None
    def __exit__(self,*args):
        self._release_camera();self.cached=None
        if self.screen:self.screen.close()
