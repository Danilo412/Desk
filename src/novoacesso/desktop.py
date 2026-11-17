"""Captura Windows e injeção de entrada apenas na sessão autorizada."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import threading
from contextlib import contextmanager
from PIL import Image
import mss

class MouseInput(ctypes.Structure):
    _fields_=[('dx',ctypes.c_int32),('dy',ctypes.c_int32),('mouseData',ctypes.c_uint32),('dwFlags',ctypes.c_uint32),('time',ctypes.c_uint32),('dwExtraInfo',ctypes.c_size_t)]
class KeyInput(ctypes.Structure):
    _fields_=[('wVk',ctypes.c_uint16),('wScan',ctypes.c_uint16),('dwFlags',ctypes.c_uint32),('time',ctypes.c_uint32),('dwExtraInfo',ctypes.c_size_t)]
class InputUnion(ctypes.Union):
    _fields_=[('mi',MouseInput),('ki',KeyInput)]
class NativeInput(ctypes.Structure):
    _anonymous_=('value',)
    _fields_=[('type',ctypes.c_uint32),('value',InputUnion)]

BUTTON_FLAGS={'left':(0x2,0x4,0),'right':(0x8,0x10,0),'middle':(0x20,0x40,0),'back':(0x80,0x100,1),'forward':(0x80,0x100,2)}
EXTENDED_KEYS={0x21,0x22,0x23,0x24,0x25,0x26,0x27,0x28,0x2d,0x2e,0x5b,0x5c,0x5d,0x6f,0xa3,0xa5}

class DesktopInputError(OSError):
    def __init__(self,code=None,backend='windows',reason='input_rejected'):
        super().__init__(code,'O Windows não aceitou a entrada nesta sessão.')
        self.input_backend=backend;self.input_reason=reason

class CursorInfo(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('flags',wintypes.DWORD),('hCursor',wintypes.HANDLE),('ptScreenPos',wintypes.POINT)]

class DesktopBackend:
    def __init__(self):
        self.lock=threading.RLock();self.rect=None;self.virtual_rect=None;self.keys=set();self.buttons=set()
        from .service_client import BrokerClient,WindowsSessionState
        self.secure=BrokerClient();self.session_lock_probe=WindowsSessionState().locked
        self.service_input_route=False;self.service_input_geometry=None
        self.user=ctypes.WinDLL("user32",use_last_error=True)
        self.user.SendInput.argtypes=[ctypes.c_uint,ctypes.POINTER(NativeInput),ctypes.c_int];self.user.SendInput.restype=ctypes.c_uint
        self.user.GetSystemMetrics.argtypes=[ctypes.c_int];self.user.GetSystemMetrics.restype=ctypes.c_int
        self.user.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];self.user.OpenInputDesktop.restype=wintypes.HANDLE
        self.user.CloseDesktop.argtypes=[wintypes.HANDLE];self.user.CloseDesktop.restype=wintypes.BOOL
        self.user.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
        self.user.GetUserObjectInformationW.restype=wintypes.BOOL
        if hasattr(self.user,'SetThreadDpiAwarenessContext'):
            self.user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p];self.user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p

    @contextmanager
    def physical_coordinates(self):
        setter=getattr(getattr(self,'user',None),'SetThreadDpiAwarenessContext',None)
        previous=setter(ctypes.c_void_p(-4)) if setter else None
        try:yield
        finally:
            if previous:setter(previous)

    def _emit(self,event):
        if self.user.SendInput(1,ctypes.byref(event),ctypes.sizeof(NativeInput))!=1:
            raise DesktopInputError(ctypes.get_last_error())
    def _mouse(self,flags,data=0,x=None,y=None):
        event=NativeInput();event.type=0;event.mi.dwFlags=flags;event.mi.mouseData=data&0xffffffff
        if x is not None:
            virtual=getattr(self,'virtual_rect',None)
            if virtual:left,top,width,height=[virtual[k] for k in ('left','top','width','height')]
            else:left,top,width,height=[self.user.GetSystemMetrics(i) for i in (76,77,78,79)]
            if width<2 or height<2:raise RuntimeError('Dimensões da área de trabalho indisponíveis.')
            event.mi.dx=max(0,min(65535,round((x-left)*65535/(width-1))));event.mi.dy=max(0,min(65535,round((y-top)*65535/(height-1))))
            event.mi.dwFlags|=0x8000|0x4000|0x2000|0x1
        self._emit(event)
    def _key(self,vk,down):
        event=NativeInput();event.type=1;event.ki.wVk=vk;event.ki.dwFlags=(0 if down else 2)|(1 if vk in EXTENDED_KEYS else 0);self._emit(event)

    def monitors(self):
        with self.physical_coordinates(),mss.MSS() as source:return [dict(m) for m in source.monitors]

    def local_desktop_state(self):
        # Read only: never switches desktop or changes its permissions.
        probe=getattr(self,'session_lock_probe',None)
        if probe and probe() is True:return 'protected'
        desktop=self.user.OpenInputDesktop(0,False,1)
        if not desktop:return 'protected'
        try:
            name=ctypes.create_unicode_buffer(256);needed=wintypes.DWORD()
            if not self.user.GetUserObjectInformationW(desktop,2,name,ctypes.sizeof(name),ctypes.byref(needed)):return 'protected'
            return 'desktop' if name.value.casefold()=='default' else 'protected'
        finally:self.user.CloseDesktop(desktop)

    def input_desktop_state(self):
        state=self.local_desktop_state()
        secure=getattr(self,'secure',None)
        return 'desktop' if state=='protected' and secure and secure.available() else state

    def begin_secure_session(self):
        self.secure.begin_session()
        # Choose once for the approved lease, avoiding a mid-drag/key route
        # change. The broker already supports Default as well as Winlogon.
        self.service_input_route=self.secure.available()
        if self.service_input_route:
            try:self.secure.input_state()
            except (OSError,ValueError):self.service_input_route=False
        self.service_input_geometry=None

    def end_secure_session(self):
        secure=getattr(self,'secure',None)
        if secure:secure.end_session()
        self.service_input_route=False;self.service_input_geometry=None

    @staticmethod
    def _geometry(rect,virtual):
        return tuple(rect[k] for k in ('left','top','width','height'))+tuple(virtual[k] for k in ('left','top','width','height'))

    def _prepare_service_input(self):
        if not self.rect or not self.virtual_rect or not hasattr(self,'capture_monitor'):
            raise DesktopInputError(None,'service','capture_required')
        expected=self._geometry(self.rect,self.virtual_rect)
        generation,captured=self.secure.input_state()
        if captured and getattr(self,'service_input_geometry',None)==(self.capture_monitor,expected,generation):return
        self.secure.release()
        _,rect,virtual=self.secure.capture(self.capture_monitor,self.capture_width)
        # Never inject using a different monitor enumeration or stale DPI
        # geometry than the frame actually shown to the viewer.
        if self._geometry(rect,virtual)!=expected:
            raise DesktopInputError(None,'service','geometry_mismatch')
        current_generation,captured=self.secure.input_state()
        if not captured or current_generation!=generation:
            raise DesktopInputError(None,'service','desktop_changed')
        self.service_input_geometry=(self.capture_monitor,expected,generation)

    def capture_source(self):
        from .capture import CaptureSource
        return CaptureSource()

    def cursor(self):
        if not hasattr(self,'_cursor_shapes'):
            self.user.LoadCursorW.argtypes=[wintypes.HINSTANCE,ctypes.c_void_p];self.user.LoadCursorW.restype=wintypes.HANDLE
            self.user.GetCursorInfo.argtypes=[ctypes.POINTER(CursorInfo)];self.user.GetCursorInfo.restype=wintypes.BOOL
            self._cursor_shapes={self.user.LoadCursorW(None,i):name for i,name in [(32512,'arrow'),(32513,'ibeam'),(32514,'wait'),(32515,'cross'),(32649,'hand'),(32646,'size_all'),(32644,'size_we'),(32645,'size_ns'),(32642,'size_nwse'),(32643,'size_nesw'),(32648,'forbidden'),(32650,'busy')]}
        info=CursorInfo();info.cbSize=ctypes.sizeof(info)
        return self._cursor_shapes.get(info.hCursor,'arrow') if self.user.GetCursorInfo(ctypes.byref(info)) and info.flags&1 else 'arrow'

    def capture(self,source,index,width):
        secure=getattr(self,'secure',None)
        if secure and secure.authorized and self.local_desktop_state()=='protected':
            image,rect,virtual=secure.capture(index,width)
            with self.lock:
                self.rect=rect;self.virtual_rect=virtual;self.capture_monitor=index;self.capture_width=width
                self.service_input_geometry=None
            if hasattr(source,'backend'):source.backend='Serviço Windows';source.unchanged=False
            return image
        with self.physical_coordinates():return self._capture_physical(source,index,width)

    def _capture_physical(self,source,index,width):
        monitors=source.monitors
        if not 0<=index<len(monitors):index=1 if len(monitors)>1 else 0
        rect=monitors[index]
        with self.lock:
            self.rect=dict(rect);self.virtual_rect=dict(monitors[0]);self.capture_monitor=index;self.capture_width=width
        if hasattr(source,'image'):image=source.image(index)
        else:
            shot=source.grab(rect);image=Image.frombytes("RGB",shot.size,shot.bgra,'raw','BGRX')
        max_height=1440 if width>1920 else 1080 if width>=1920 else 720 if width>=1280 else 1080
        ratio=min(1,width/image.width,max_height/image.height)
        if ratio<1:image=image.resize((max(1,int(image.width*ratio)),max(1,int(image.height*ratio))),Image.Resampling.LANCZOS)
        return image

    def input(self,data):
        with self.lock,self.physical_coordinates():
            secure=getattr(self,'secure',None)
            if secure and secure.authorized and (getattr(self,'service_input_route',False) or self.local_desktop_state()=='protected'):
                if data.get('event')=='release':self.release();return
                try:
                    if getattr(self,'service_input_route',False):self._prepare_service_input()
                    secure.input(data)
                except DesktopInputError:raise
                except (OSError,ValueError) as error:raise DesktopInputError(getattr(error,'winerror',None) or getattr(error,'errno',None),'service','service_unavailable') from error
                return
            kind=data.get("event")
            if kind in ("move","button"):
                x,y=data.get("x"),data.get("y")
                if type(x) not in (int,float) or type(y) not in (int,float) or not (0<=x<=1 and 0<=y<=1) or not self.rect:return
                r=self.rect
                px=r['left']+round(x*(r['width']-1));py=r['top']+round(y*(r['height']-1))
                if kind=="button":
                    button=data.get("button");down=data.get("down")
                    if button not in BUTTON_FLAGS or type(down) is not bool:return
                    flags=BUTTON_FLAGS[button];self._mouse(flags[0 if down else 1],flags[2],px,py)
                    (self.buttons.add if down else self.buttons.discard)(button)
                else:self._mouse(0,x=px,y=py)
            elif kind=="wheel":
                delta=data.get("delta")
                if type(delta) is int and abs(delta)<=1200:self._mouse(0x800,delta)
            elif kind=="key":
                vk=data.get("vk");down=data.get("down")
                if type(vk) is not int or not 1<=vk<=254 or type(down) is not bool:return
                self._key(vk,down)
                (self.keys.add if down else self.keys.discard)(vk)
            elif kind=="release":self.release()

    def release(self):
        secure=getattr(self,'secure',None)
        if secure:secure.release()
        with self.lock,self.physical_coordinates():
            for key in self.keys:
                try:self._key(key,False)
                except OSError:pass
            for button in self.buttons:
                flags=BUTTON_FLAGS[button]
                try:self._mouse(flags[1],flags[2])
                except OSError:pass
            self.keys.clear();self.buttons.clear()
