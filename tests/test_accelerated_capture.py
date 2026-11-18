"""Stubbed GPU/MSS only. Never acquires a real desktop or injects input."""
import sys,threading
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from novoacesso import capture
from novoacesso.capture import CaptureSource
from novoacesso.desktop import DesktopBackend


def install_stubs(monkeypatch,frames,monitors=None):
    calls=[]
    class Camera:
        def grab(self):calls.append('gpu_grab');return frames.pop(0)
        def release(self):calls.append('gpu_release')
    class Screen:
        def __init__(self):self.monitors=monitors or [dict(left=0,top=0,width=129,height=67)]*2
        def grab(self,rect):
            calls.append('mss_grab');size=rect['width'],rect['height']
            return SimpleNamespace(size=size,bgra=b'\0\0\0\xff'*(size[0]*size[1]))
        def close(self):calls.append('mss_close')
    def create(**kwargs):calls.append(kwargs);return Camera()
    monkeypatch.setattr(capture.os,'name','nt')
    monkeypatch.delenv('NOVOACESSO_CAPTURE',raising=False)
    monkeypatch.setattr(capture.mss,'MSS',lambda **kw:Screen())
    monkeypatch.setitem(sys.modules,'dxcam',SimpleNamespace(create=create))
    monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(CoInitialize=lambda:calls.append('com_init'),CoUninitialize=lambda:calls.append('com_release')))
    return calls


@pytest.mark.parametrize('control',[True,False])
def test_hardware_capture_remains_available_with_separate_cursor(control,monkeypatch):
    frame=np.zeros((67,129,4),np.uint8);frame[:,:,2]=220;frame[:,:,3]=255
    calls=install_stubs(monkeypatch,[frame,None])
    with CaptureSource() as source:
        source.separate_cursor=control
        image=source.image(1)
        assert source.backend=='DXGI' and image.getpixel((80,40))==(220,0,0)
        assert source.image(1) is image and source.unchanged
        assert 'mss_grab' not in calls
    options=next(call for call in calls if isinstance(call,dict))
    assert options['backend']=='dxgi' and options['output_color']=='BGRA'
    assert calls.count('gpu_release')==calls.count('com_release')==1


def test_size_mismatch_falls_back_without_showing_wrong_gpu_output(monkeypatch):
    calls=install_stubs(monkeypatch,[np.zeros((32,32,4),np.uint8)])
    with CaptureSource() as source:
        source.separate_cursor=True
        assert source.image(1).size==(129,67)
        assert source.backend=='MSS' and source.dxgi_failed and source.camera is None
        assert source.image(1).size==(129,67)
    assert calls.count('gpu_grab')==1 and calls.count('mss_grab')==2


def test_multiple_monitors_and_explicit_mss_keep_exact_monitor(monkeypatch):
    monitors=[dict(left=0,top=0,width=258,height=67),dict(left=0,top=0,width=129,height=67),dict(left=129,top=0,width=129,height=67)]
    calls=install_stubs(monkeypatch,[],monitors)
    with CaptureSource() as source:
        source.separate_cursor=True;assert source.image(2).size==(129,67) and source.backend=='MSS'
    assert not any(isinstance(c,dict) for c in calls)
    calls=install_stubs(monkeypatch,[]);monkeypatch.setenv('NOVOACESSO_CAPTURE','mss')
    with CaptureSource() as source:assert source.image(1).size==(129,67)
    assert not any(isinstance(c,dict) for c in calls)


def test_gpu_failure_keeps_mss_without_repeated_initialization(monkeypatch):
    calls=install_stubs(monkeypatch,[])
    with CaptureSource() as source:
        source.separate_cursor=True
        for _ in range(3):assert source.image(1).size==(129,67)
        assert source.dxgi_failed and source.backend=='MSS'
    assert calls.count('com_init')==1 and calls.count('mss_grab')==3


def test_stage_metrics_are_numeric_without_changing_frame_geometry():
    value=DesktopBackend.__new__(DesktopBackend);value.lock=threading.RLock()
    source=SimpleNamespace(monitors=[dict(left=0,top=0,width=129,height=67)]*2,image=lambda index:Image.new('RGB',(129,67),'navy'))
    result=value.capture(source,1,1280)
    assert result.size==(129,67) and value.rect['width']==129
    assert set(value.last_capture_metrics)=={'capture_probe_ms','capture_grab_ms','capture_scale_ms'}
    assert all(type(v) is float and v>=0 for v in value.last_capture_metrics.values())
