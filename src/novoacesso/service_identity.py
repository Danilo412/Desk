"""Read-only SCM identity checks for the administrator-installed broker.

Ordinary clients must not open a LocalSystem process/token or enable debug
privileges. Match the kernel-reported pipe PID/session to the local SCM's
running, own-process LocalSystem service and its pinned image instead.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes

SERVICE_NAME='DeskScreenBroker'

class ServiceStatus(ctypes.Structure):
    _fields_=[(name,wintypes.DWORD) for name in ('kind','state','accepted','exit_code','specific_exit','checkpoint','wait_hint','pid','flags')]

class ServiceConfig(ctypes.Structure):
    _fields_=[('kind',wintypes.DWORD),('start',wintypes.DWORD),('error',wintypes.DWORD),
              ('command',wintypes.LPWSTR),('group',wintypes.LPWSTR),('tag',wintypes.DWORD),
              ('dependencies',wintypes.LPWSTR),('account',wintypes.LPWSTR),('display',wintypes.LPWSTR)]

def service_identity_snapshot(service_name=SERVICE_NAME):
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    signatures={
        'OpenSCManagerW':([wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD],wintypes.HANDLE),
        'OpenServiceW':([wintypes.HANDLE,wintypes.LPCWSTR,wintypes.DWORD],wintypes.HANDLE),
        'QueryServiceStatusEx':([wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)],wintypes.BOOL),
        'QueryServiceConfigW':([wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)],wintypes.BOOL),
        'CloseServiceHandle':([wintypes.HANDLE],wintypes.BOOL),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(api,name);fn.argtypes=args;fn.restype=result
    manager=api.OpenSCManagerW(None,None,1)  # CONNECT only, local SCM
    if not manager:raise ctypes.WinError(ctypes.get_last_error())
    service=None
    try:
        service=api.OpenServiceW(manager,service_name,1|4)  # QUERY_CONFIG | QUERY_STATUS
        if not service:raise ctypes.WinError(ctypes.get_last_error())
        status=ServiceStatus();needed=wintypes.DWORD()
        if not api.QueryServiceStatusEx(service,0,ctypes.byref(status),ctypes.sizeof(status),ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.set_last_error(0)
        if api.QueryServiceConfigW(service,None,0,ctypes.byref(needed)) or ctypes.get_last_error()!=122:
            raise OSError('Resposta de configuração do serviço inválida.')
        if not ctypes.sizeof(ServiceConfig)<=needed.value<=8192:raise ValueError('Configuração do serviço fora dos limites.')
        buffer=ctypes.create_string_buffer(needed.value)
        if not api.QueryServiceConfigW(service,buffer,len(buffer),ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        config=ctypes.cast(buffer,ctypes.POINTER(ServiceConfig)).contents
        return dict(kind=status.kind,state=status.state,pid=status.pid,config_kind=config.kind,
                    command=config.command or '',account=config.account or '')
    finally:
        if service:api.CloseServiceHandle(service)
        api.CloseServiceHandle(manager)

def validate_service_identity(config,snapshot,server_pid,server_session):
    expected='"'+config['ServicePath']+'" --service'
    if (type(server_pid) is not int or server_pid<=0 or server_session!=0 or
        snapshot.get('pid')!=server_pid or snapshot.get('state')!=4 or
        snapshot.get('kind')!=0x10 or snapshot.get('config_kind')!=0x10 or
        snapshot.get('account','').casefold()!='localsystem' or
        snapshot.get('command','').casefold()!=expected.casefold()):
        raise OSError('Identidade do serviço não corresponde à instalação de administrador.')
