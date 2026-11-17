"""Client of the optional, signed LocalSystem screen broker.

The broker owns no network socket. Only an already-approved host Peer opens
this local lease. Production server/client identities are pinned by the
administrator's protected installation, never by a per-user setting.
"""
from __future__ import annotations
import ctypes,hashlib,math,os,struct,sys,threading,time
from pathlib import Path
from ctypes import wintypes
from PIL import Image

MAX_REPLY=32*1024*1024
FRAME=struct.Struct('<8iHHI')
SERVICE_KEY=r'SOFTWARE\DeskHost'
BUTTONS={'left':0,'right':1,'middle':2,'back':3,'forward':4}

def session_locked_flag(data,session_id):
    # WTSINFOEXW is 64-bit aligned: Level, padding, Level1.SessionId,
    # SessionState, SessionFlags. Never decode usernames or other fields.
    if len(data)<20:return None
    level,session,state,flags=struct.unpack_from('<I4xIIi',data)
    if level!=1 or session!=session_id or flags not in (0,1):return None
    return flags==0

class WindowsSessionState:
    def __init__(self):
        self.api=ctypes.WinDLL('wtsapi32',use_last_error=True);self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.WTSQuerySessionInformationW.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.DWORD)];self.api.WTSQuerySessionInformationW.restype=wintypes.BOOL
        self.api.WTSFreeMemory.argtypes=[ctypes.c_void_p];self.api.WTSFreeMemory.restype=None
        self.kernel.ProcessIdToSessionId.argtypes=[wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)];self.kernel.ProcessIdToSessionId.restype=wintypes.BOOL
        session=wintypes.DWORD();self.session=session.value if self.kernel.ProcessIdToSessionId(os.getpid(),ctypes.byref(session)) else None
        self.lock=threading.Lock();self.next_check=0.;self.cached=None
    def locked(self):
        if self.session is None:return None
        with self.lock:
            now=time.monotonic()
            if now<self.next_check:return self.cached
            pointer=ctypes.c_void_p();size=wintypes.DWORD();self.next_check=now+.1;self.cached=None
            if self.api.WTSQuerySessionInformationW(None,self.session,25,ctypes.byref(pointer),ctypes.byref(size)):
                try:
                    if 20<=size.value<=65536:self.cached=session_locked_flag(ctypes.string_at(pointer,20),self.session)
                finally:self.api.WTSFreeMemory(pointer)
            return self.cached

def input_packet(value):
    kind=value.get('event')
    if kind=='release':return b'\x04\x05'
    if kind in ('move','button'):
        x,y=value.get('x'),value.get('y')
        if any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in (x,y)):raise ValueError('Coordenadas inválidas.')
        if kind=='move':return b'\x04\x01'+struct.pack('<dd',x,y)
        button,down=value.get('button'),value.get('down')
        if button not in BUTTONS or type(down) is not bool:raise ValueError('Botão inválido.')
        return bytes((4,3,BUTTONS[button],int(down)))+struct.pack('<dd',x,y)
    if kind=='key':
        vk,down=value.get('vk'),value.get('down')
        if type(vk) is not int or not 1<=vk<=254 or type(down) is not bool:raise ValueError('Tecla inválida.')
        return b'\x04\x02'+struct.pack('<HB',vk,int(down))
    if kind=='wheel':
        delta=value.get('delta')
        if type(delta) is not int or abs(delta)>1200:raise ValueError('Rolagem inválida.')
        return b'\x04\x04'+struct.pack('<i',delta)
    raise ValueError('Entrada indisponível.')

def decode_frame(reply,max_width,max_height):
    if not isinstance(reply,bytes) or not 1+FRAME.size<=len(reply)<=MAX_REPLY or reply[0]!=0:raise OSError('Captura pelo serviço indisponível.')
    left,top,width,height,vl,vt,vw,vh,w,h,stride=FRAME.unpack_from(reply,1)
    if not (1<=width<=32768 and 1<=height<=32768 and 2<=vw<=32768 and 2<=vh<=32768 and vl<=left and vt<=top and left+width<=vl+vw and top+height<=vt+vh):raise ValueError('Geometria do serviço inválida.')
    if not (1<=w<=max_width<=3840 and 1<=h<=max_height<=2160) or stride!=(w*3+3)&~3 or len(reply)!=1+FRAME.size+stride*h:raise ValueError('Imagem do serviço fora dos limites.')
    image=Image.frombytes('RGB',(w,h),reply[1+FRAME.size:],'raw','BGR',stride,1)
    return image,dict(left=left,top=top,width=width,height=height),dict(left=vl,top=vt,width=vw,height=vh)

def installed_configuration():
    if os.name!='nt':return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,SERVICE_KEY,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            result={name:winreg.QueryValueEx(key,name)[0] for name in ('OwnerSid','ClientPath','ClientHash','ServiceHash')}
            try:result['TrustMode']=winreg.QueryValueEx(key,'TrustMode')[0]
            except FileNotFoundError:result['TrustMode']='publisher'
        if any(not isinstance(v,str) for v in result.values()):return None
        for name in ('ClientHash','ServiceHash'):
            if len(result[name])!=64 or any(c not in '0123456789abcdef' for c in result[name]):return None
        if not result['OwnerSid'].startswith('S-1-5-21-') or not result['OwnerSid'][9:].replace('-','').isdigit():return None
        result['ServicePath']=str(Path(os.environ['ProgramFiles'])/'DeskHost/DeskHost.exe')
        if os.path.normcase(os.path.abspath(result['ClientPath']))!=os.path.normcase(os.path.abspath(sys.executable)):return None
        if result['TrustMode'] not in ('publisher','fixed'):return None
        if result['TrustMode']=='fixed' and hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()!=result['ClientHash']:return None
        # The service revalidates the running image's trusted publisher.
        # Do not disable it after an ordinary signed update of Desk.exe.
        return result
    except (OSError,ValueError,KeyError):return None

class OVERLAPPED(ctypes.Structure):
    _fields_=[('Internal',ctypes.c_size_t),('InternalHigh',ctypes.c_size_t),('Offset',wintypes.DWORD),('OffsetHigh',wintypes.DWORD),('hEvent',wintypes.HANDLE)]

class WindowsPipe:
    """Overlapped, bounded I/O; closing a lease cancels pending requests."""
    def __init__(self,config):
        self.api=ctypes.WinDLL('kernel32',use_last_error=True);self.handle=None;self.state_lock=threading.Lock();self.closing=False;self.active=0
        signatures={
            'WaitNamedPipeW':([wintypes.LPCWSTR,wintypes.DWORD],wintypes.BOOL),
            'CreateFileW':([wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE],wintypes.HANDLE),
            'CloseHandle':([wintypes.HANDLE],wintypes.BOOL),
            'CreateEventW':([ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR],wintypes.HANDLE),
            'ReadFile':([wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(OVERLAPPED)],wintypes.BOOL),
            'WriteFile':([wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(OVERLAPPED)],wintypes.BOOL),
            'WaitForSingleObject':([wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD),
            'GetOverlappedResult':([wintypes.HANDLE,ctypes.POINTER(OVERLAPPED),ctypes.POINTER(wintypes.DWORD),wintypes.BOOL],wintypes.BOOL),
            'CancelIoEx':([wintypes.HANDLE,ctypes.POINTER(OVERLAPPED)],wintypes.BOOL),
            'GetNamedPipeServerProcessId':([wintypes.HANDLE,ctypes.POINTER(wintypes.ULONG)],wintypes.BOOL),
            'GetNamedPipeServerSessionId':([wintypes.HANDLE,ctypes.POINTER(wintypes.ULONG)],wintypes.BOOL),
        }
        for name,(args,result) in signatures.items():fn=getattr(self.api,name);fn.argtypes=args;fn.restype=result
        name=r'\\.\pipe\DeskHost.'+config['OwnerSid']
        if not self.api.WaitNamedPipeW(name,2000):raise ctypes.WinError(ctypes.get_last_error())
        handle=self.api.CreateFileW(name,0xC0000000,0,None,3,0x40000000|0x00110000,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        self.handle=handle
        try:self.verify_server(config)
        except Exception:self.close();raise

    def verify_server(self,config):
        from .service_identity import service_identity_snapshot,validate_service_identity
        pid=wintypes.ULONG();session=wintypes.DWORD()
        if not self.api.GetNamedPipeServerProcessId(self.handle,ctypes.byref(pid)) or not self.api.GetNamedPipeServerSessionId(self.handle,ctypes.byref(session)):
            raise ctypes.WinError(ctypes.get_last_error())
        before=service_identity_snapshot()
        validate_service_identity(config,before,pid.value,session.value)
        if hashlib.sha256(Path(config['ServicePath']).read_bytes()).hexdigest()!=config['ServiceHash']:
            raise OSError('O serviço não corresponde à instalação autorizada.')
        after=service_identity_snapshot()
        validate_service_identity(config,after,pid.value,session.value)
        if before!=after:raise OSError('O serviço mudou durante a verificação de identidade.')

    def _io(self,data,size,write,deadline):
        with self.state_lock:
            handle=self.handle
            if handle is None or self.closing:raise OSError('Serviço desconectado.')
            self.active+=1
        event=None
        try:
            event=self.api.CreateEventW(None,True,False,None)
            if not event:raise OSError('Evento de serviço indisponível.')
            overlapped=OVERLAPPED();overlapped.hEvent=event;count=wintypes.DWORD();buffer=ctypes.create_string_buffer(data,size) if write else ctypes.create_string_buffer(size)
            fn=self.api.WriteFile if write else self.api.ReadFile
            if not fn(handle,buffer,size,ctypes.byref(count),ctypes.byref(overlapped)):
                if ctypes.get_last_error()!=997:raise OSError('Falha de comunicação com o serviço.')
                milliseconds=max(0,int((deadline-time.monotonic())*1000))
                if self.api.WaitForSingleObject(event,milliseconds)!=0:
                    self.api.CancelIoEx(handle,ctypes.byref(overlapped));self.api.GetOverlappedResult(handle,ctypes.byref(overlapped),ctypes.byref(count),True)
                    raise TimeoutError('O serviço não respondeu dentro do prazo.')
            if not self.api.GetOverlappedResult(handle,ctypes.byref(overlapped),ctypes.byref(count),False) or count.value==0:raise OSError('O serviço encerrou a comunicação.')
            return count.value if write else buffer.raw[:count.value]
        finally:
            if event:self.api.CloseHandle(event)
            with self.state_lock:
                self.active-=1
                if self.closing and self.active==0 and self.handle is not None:self.api.CloseHandle(self.handle);self.handle=None

    def exchange(self,payload,timeout):
        if not 1<=len(payload)<=512:raise ValueError('Solicitação de serviço inválida.')
        deadline=time.monotonic()+timeout;data=struct.pack('<I',len(payload))+payload
        while data:data=data[self._io(data,len(data),True,deadline):]
        def read_exact(size):
            chunks=[];remaining=size
            while remaining:
                chunk=self._io(None,remaining,False,deadline);chunks.append(chunk);remaining-=len(chunk)
            return b''.join(chunks)
        length=struct.unpack('<I',read_exact(4))[0]
        if not 1<=length<=MAX_REPLY:raise ValueError('Resposta do serviço fora dos limites.')
        return read_exact(length)

    def close(self):
        with self.state_lock:
            self.closing=True;handle=self.handle
            if handle is not None:
                self.api.CancelIoEx(handle,None)
                if self.active==0:self.api.CloseHandle(handle);self.handle=None

class BrokerClient:
    def __init__(self,connector=None,configuration=None,configuration_loader=None):
        self.connector=connector or WindowsPipe
        self.configuration_loader=configuration_loader or ((lambda:configuration) if configuration is not None else installed_configuration)
        self.config=self.configuration_loader()
        self.authorized=False;self.connection=None;self.lock=threading.RLock();self.state_lock=threading.Lock();self.last_error='';self.last_error_code=None;self.lease=0
    @property
    def installed(self):return self.config is not None
    def begin_session(self):
        # Installation/rebinding may have happened while the GUI was open.
        # A new approved session gets a fresh configuration and IPC lease.
        self.end_session()
        configuration=self.configuration_loader()
        with self.state_lock:self.config=configuration;self.authorized=True;self.lease+=1
    def end_session(self):
        with self.state_lock:
            self.authorized=False;self.lease+=1;connection=self.connection;self.connection=None
        if connection:connection.close()
    def _load_missing_configuration(self):
        with self.state_lock:
            if not self.authorized or self.config is not None:return
            lease=self.lease
        configuration=self.configuration_loader()
        with self.state_lock:
            if self.authorized and self.lease==lease and self.config is None:self.config=configuration
    def _request(self,payload,timeout=2):
        with self.lock:
            self._load_missing_configuration()
            with self.state_lock:
                if not self.authorized or not self.config:raise OSError('O serviço não está instalado e autorizado para esta sessão.')
                lease=self.lease
                connection=self.connection
            try:
                if connection is None:
                    connection=self.connector(self.config)
                    with self.state_lock:
                        if not self.authorized or self.lease!=lease:
                            connection.close();connection=None
                            raise OSError('A autorização da sessão foi encerrada.')
                        self.connection=connection
                reply=connection.exchange(payload,timeout)
                with self.state_lock:
                    if not self.authorized or self.lease!=lease:raise OSError('A autorização da sessão foi encerrada.')
                if not reply or reply[0]!=0:raise OSError('O serviço recusou esta operação.')
                self.last_error='';self.last_error_code=None;return reply
            except Exception as error:
                self.last_error='Serviço indisponível. Confira a assinatura, a instalação e a autorização de administrador.'
                code=getattr(error,'winerror',None)
                if type(code) is not int:code=getattr(error,'errno',None)
                self.last_error_code=code if type(code) is int and 0<=code<=65535 else None
                with self.state_lock:
                    if self.connection is connection:self.connection=None
                if connection:connection.close()
                raise
    def available(self):
        if not self.authorized:return False
        self._load_missing_configuration()
        if not self.installed:return False
        try:return self._request(b'\x01') in (b'\0\0',b'\0\1')
        except (OSError,ValueError):return False
    def input_state(self):
        reply=self._request(b'\x06')
        if len(reply)!=7:raise ValueError('Estado do serviço incompatível.')
        desktop,captured,generation=struct.unpack('<BBI',reply[1:])
        if desktop not in (0,1) or captured not in (0,1) or generation<1:raise ValueError('Estado do serviço inválido.')
        return generation,bool(captured)
    def capture(self,index,width):
        height=1440 if width>1920 else 1080 if width>=1920 else 720 if width>=1280 else 1080
        request=struct.pack('<BiHHB',3,index,width,height,1)
        return decode_frame(self._request(request,5),width,height)
    def input(self,value):self._request(input_packet(value))
    def release(self):
        with self.state_lock:connected=self.connection is not None
        if self.authorized and connected:
            try:self._request(b'\x05')
            except (OSError,ValueError):pass
