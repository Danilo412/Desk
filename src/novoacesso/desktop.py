"""Captura Windows e injeção de entrada apenas na sessão autorizada."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import threading
from PIL import Image
import mss

class CursorInfo(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('flags',wintypes.DWORD),('hCursor',wintypes.HANDLE),('ptScreenPos',wintypes.POINT)]

class DesktopBackend:
    def __init__(self):
        self.lock=threading.RLock();self.rect=None;self.keys=set();self.buttons=set()
        self.user=ctypes.WinDLL("user32",use_last_error=True)
        self.user.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
        self.user.SetCursorPos.restype=wintypes.BOOL
        self.user.keybd_event.argtypes=[wintypes.BYTE,wintypes.BYTE,wintypes.DWORD,ctypes.c_size_t]
        self.user.mouse_event.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_size_t]

    def monitors(self):
        with mss.MSS() as source:return [dict(m) for m in source.monitors]

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
        monitors=source.monitors
        if not 0<=index<len(monitors):index=1 if len(monitors)>1 else 0
        rect=monitors[index]
        with self.lock:self.rect=dict(rect)
        if hasattr(source,'image'):image=source.image(index)
        else:
            shot=source.grab(rect);image=Image.frombytes("RGB",shot.size,shot.bgra,'raw','BGRX')
        max_height=1440 if width>1920 else 1080 if width>=1920 else 720 if width>=1280 else 1080
        ratio=min(1,width/image.width,max_height/image.height)
        if ratio<1:image=image.resize((max(1,int(image.width*ratio)),max(1,int(image.height*ratio))),Image.Resampling.LANCZOS)
        return image

    def input(self,data):
        with self.lock:
            kind=data.get("event")
            if kind in ("move","button"):
                x,y=data.get("x"),data.get("y")
                if type(x) not in (int,float) or type(y) not in (int,float) or not (0<=x<=1 and 0<=y<=1) or not self.rect:return
                r=self.rect
                self.user.SetCursorPos(r["left"]+round(x*(r["width"]-1)),r["top"]+round(y*(r["height"]-1)))
                if kind=="button":
                    button=data.get("button");down=data.get("down")
                    flags={"left":(0x2,0x4),"right":(0x8,0x10),"middle":(0x20,0x40)}
                    if button not in flags or type(down) is not bool:return
                    self.user.mouse_event(flags[button][0 if down else 1],0,0,0,0)
                    (self.buttons.add if down else self.buttons.discard)(button)
            elif kind=="wheel":
                delta=data.get("delta")
                if type(delta) is int and abs(delta)<=1200:self.user.mouse_event(0x800,0,0,delta&0xffffffff,0)
            elif kind=="key":
                vk=data.get("vk");down=data.get("down")
                if type(vk) is not int or not 1<=vk<=254 or type(down) is not bool:return
                self.user.keybd_event(vk,0,0 if down else 2,0)
                (self.keys.add if down else self.keys.discard)(vk)
            elif kind=="release":self.release()

    def release(self):
        with self.lock:
            for key in self.keys:self.user.keybd_event(key,0,2,0)
            for button in self.buttons:self.user.mouse_event({"left":4,"right":16,"middle":64}[button],0,0,0,0)
            self.keys.clear();self.buttons.clear()
