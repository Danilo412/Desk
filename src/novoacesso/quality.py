"""Perfis de transmissão e preferências persistidas por computador."""
PROFILES=(('Full HD · 1080p / 30 FPS',1920,30),('Full HD · 1080p / 60 FPS',1920,60),('QHD · 1440p / 30 FPS',2560,30),('QHD · 1440p / 60 FPS',2560,60),('Economia · 720p / 30 FPS',1280,30),('Rede distante · 960p / 24 FPS',960,24))
WIDTHS=(640,960,1280,1920,2560)
FPS=(15,24,30,60)
MAX_WIDTH=2560;MAX_HEIGHT=1440;MAX_PIXELS=MAX_WIDTH*MAX_HEIGHT

def preferences(value=None):
    value=value if isinstance(value,dict) else {}
    width=value.get('width',1920);fps=value.get('fps',30);codec=value.get('codec','auto')
    if (width,fps) not in {(w,f) for _,w,f in PROFILES}:width,fps=1920,30
    if codec not in ('auto','deflate','vp8'):codec='auto'
    display=value.get('display','fit')
    if display not in ('fit','original','stretch'):display='fit'
    result=dict(width=width,fps=fps,codec=codec,auto_reconnect=value.get('auto_reconnect',True) is True,display=display)
    if value.get('start_fullscreen') is True:result['start_fullscreen']=True
    return result
