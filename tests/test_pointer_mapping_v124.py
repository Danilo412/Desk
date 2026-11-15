import ctypes,threading
from types import SimpleNamespace
import pytest
from PIL import Image
from PySide6.QtCore import QPointF
from novoacesso.desktop import DesktopBackend,NativeInput
from novoacesso.app import RemoteCanvas

def test_mouse_uses_captured_physical_desktop_instead_of_dpi_virtualized_metrics():
    events=[]
    class User:
        # 150% scaling: logical metrics differ from the physical capture.
        def GetSystemMetrics(self,key):return {76:0,77:0,78:1280,79:720}[key]
        def SendInput(self,count,pointer,size):events.append(NativeInput.from_buffer_copy(ctypes.string_at(pointer,size)));return count
    backend=DesktopBackend.__new__(DesktopBackend);backend.user=User();backend.lock=threading.RLock();backend.rect=None;backend.keys=set();backend.buttons=set()
    image=Image.new('RGB',(1920,1080));source=SimpleNamespace(monitors=[dict(left=0,top=0,width=1920,height=1080)]*2,image=lambda index:image)
    backend.capture(source,1,1920)
    backend.input(dict(event='button',x=.5,y=.5,button='left',down=True))
    assert abs(events[-1].mi.dx-32768)<50 and abs(events[-1].mi.dy-32768)<70

@pytest.mark.parametrize('mode',('fit','stretch','original'))
def test_pointer_tracks_current_geometry_even_before_repaint(mode):
    canvas=RemoteCanvas();canvas.allow_control=True;canvas.display_mode=mode
    canvas.set_frame(Image.new('RGB',(1920,1080)));canvas.resize(640,480)
    # Simulate a cached rectangle from the preceding frame, then resize
    # without showing the widget (there is no intervening paint event).
    from PySide6.QtCore import QRectF
    canvas.rect=QRectF(0,60,640,360);canvas.resize(1280,720)
    try:
        point=canvas.point(SimpleNamespace(position=lambda:QPointF(canvas.width()/2,canvas.height()/2)))
        assert abs(point['x']-.5)<.002 and abs(point['y']-.5)<.002
    finally:canvas.close()

@pytest.mark.parametrize('index,point,expected',[(1,(0,0),(2560/4480,0)),(1,(1,1),(1,1079/1439)),(2,(0,0),(0,0)),(2,(1,1),(2559/4479,1))])
def test_negative_monitor_origin_and_scaled_capture_keep_physical_targets(index,point,expected):
    events=[]
    class User:
        def GetSystemMetrics(self,key):raise AssertionError('Must use capture coordinates, not virtualized metrics')
        def SendInput(self,count,pointer,size):events.append(NativeInput.from_buffer_copy(ctypes.string_at(pointer,size)));return count
    rectangles=[dict(left=-2560,top=0,width=4480,height=1440),dict(left=0,top=0,width=1920,height=1080),dict(left=-2560,top=0,width=2560,height=1440)]
    source=SimpleNamespace(monitors=rectangles,image=lambda i:Image.new('RGB',(rectangles[i]['width'],rectangles[i]['height'])))
    backend=DesktopBackend.__new__(DesktopBackend);backend.user=User();backend.lock=threading.RLock();backend.rect=None;backend.keys=set();backend.buttons=set()
    backend.capture(source,index,1280);backend.input(dict(event='button',x=point[0],y=point[1],button='left',down=True))
    assert abs(events[-1].mi.dx/65535-expected[0])<.001 and abs(events[-1].mi.dy/65535-expected[1])<.001
