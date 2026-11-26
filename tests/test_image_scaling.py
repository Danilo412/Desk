"""Synthetic pixels and mock providers; never captures or injects a desktop."""
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image,ImageDraw
from novoacesso.image_scaling import ScreenScaler
from novoacesso.desktop import DesktopBackend


@pytest.mark.parametrize('size,target',[
    ((2560,1440),(1920,1080)),((3840,2160),(1920,1080)),((3840,2160),(2560,1440)),
    ((2501,1403),(1920,1080)),((1536,2048),(810,1080)),((1920,1200),(1280,800)),
    ((129,67),(65,33)),((1920,1080),(1920,1080)),((1920,1080),(1280,720))])
def test_parallel_result_matches_whole_image_lanczos_without_strip_seams(size,target):
    image=Image.new('RGB',size,(210,220,230));draw=ImageDraw.Draw(image)
    rng=np.random.default_rng(32)
    for y in (0,size[1]//4,size[1]//2,3*size[1]//4,size[1]-180):
        if y<0:continue
        image.paste(Image.fromarray(rng.integers(0,256,(min(160,size[1]-y),min(210,size[0]),3),np.uint8)),(0,y))
    draw.line((0,0,size[0]-1,size[1]-1),fill='navy',width=3)
    scaler=ScreenScaler(workers=4)
    try:
        assert scaler.resize(image,target).tobytes()==image.resize(target,Image.Resampling.LANCZOS).tobytes()
    finally:scaler.close()


def test_cached_frame_requires_provider_confirmation_identity_and_geometry():
    image=Image.new('RGB',(2560,1440),'navy');scaler=ScreenScaler(4)
    try:
        result=scaler.resize(image,(1920,1080),'monitor1')
        assert scaler.resize(image,(1920,1080),'monitor1',True) is result and scaler.last_cached
        image.putpixel((100,100),(255,0,0))
        fresh=scaler.resize(image,(1920,1080),'monitor1',False)
        assert fresh.tobytes()!=result.tobytes()
        assert not scaler.last_cached
        scaler.resize(image,(1920,1080),'monitor2',True);assert not scaler.last_cached
        scaler.resize(image.copy(),(1920,1080),'monitor2',True);assert not scaler.last_cached
        resized=scaler.resize(image,(1280,720),'monitor2',True)
        assert not scaler.last_cached and resized.size==(1280,720)
    finally:scaler.close()
    assert scaler.previous is None and scaler.result is None and scaler.pool is None


def test_parallel_worker_error_falls_back_to_same_full_quality(monkeypatch):
    image=Image.new('RGB',(2560,1440),'orange');original=Image.Image.resize
    def resize(self,size,resample=None,box=None,**kwargs):
        if box is not None:raise RuntimeError('synthetic strip failure')
        return original(self,size,resample,box,**kwargs)
    monkeypatch.setattr(Image.Image,'resize',resize)
    scaler=ScreenScaler(4)
    try:
        output=scaler.resize(image,(1920,1080))
        assert scaler.failed and scaler.pool is None
        assert output.tobytes()==original(image,(1920,1080),Image.Resampling.LANCZOS).tobytes()
    finally:scaler.close()


def test_scaled_capture_keeps_native_input_geometry_and_caches_unchanged():
    value=DesktopBackend.__new__(DesktopBackend);value.lock=threading.RLock()
    image=Image.new('RGB',(3840,2160),'navy')
    rect=dict(left=-3840,top=0,width=3840,height=2160)
    source=SimpleNamespace(monitors=[dict(left=-3840,top=0,width=5760,height=2160),rect],image=lambda index:image,unchanged=False)
    try:
        result=value.capture(source,1,1920)
        assert result.size==(1920,1080) and value.rect==rect and value.capture_width==1920
        source.unchanged=True
        assert value.capture(source,1,1920) is result and value._screen_scaler.last_cached
        source.unchanged=False;image.paste('green',(10,10,80,80))
        assert value.capture(source,1,1920).tobytes()!=result.tobytes()
    finally:value._screen_scaler.close()


def test_capture_context_closes_scaler_without_installing_service(monkeypatch):
    from contextlib import nullcontext
    from novoacesso import capture
    calls=[];value=DesktopBackend.__new__(DesktopBackend)
    value._screen_scaler=SimpleNamespace(close=lambda:calls.append('close'))
    monkeypatch.setattr(capture,'CaptureSource',lambda:nullcontext(SimpleNamespace()))
    with value.capture_source():pass
    assert calls==['close'] and value._screen_scaler is None
