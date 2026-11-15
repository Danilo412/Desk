"""Small, typed remote requests. Every privileged action requires local approval."""
import math,secrets,threading,time
from pathlib import Path
from .wire import ProtocolError

CAPABILITIES={'system_info','restart','print','whiteboard'}
INFO_FIELDS={'Computador','Sistema','Arquitetura','Processador','Memória RAM','Disco do sistema livre','Monitores'}

def system_information(monitors):
    import ctypes,os,platform,shutil,socket
    memory='Não informado'
    if os.name=='nt':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(name,ctypes.c_ulonglong) for name in ('total','available','pagefile','available_pagefile','virtual','available_virtual','extended')]]
        value=Memory();value.length=ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):memory=f'{value.total/1024**3:.1f} GB'
    drive=Path.home().anchor or '/'
    return {'Computador':socket.gethostname()[:120],'Sistema':platform.platform()[:160],
            'Arquitetura':platform.machine()[:80],'Processador':platform.processor()[:160] or 'Não informado',
            'Memória RAM':memory,'Disco do sistema livre':f'{shutil.disk_usage(drive).free/1024**3:.1f} GB',
            'Monitores':str(max(0,len(monitors)-1))}

def validate_stroke(value):
    if not isinstance(value,dict) or value.get('shape') not in ('freehand','line','rectangle','ellipse','arrow'):raise ProtocolError('Desenho inválido.')
    if value.get('color') not in ('#ef443b','#ffc857','#57bd7a','#59a8ff','#e6e6e6','#151515'):raise ProtocolError('Cor de anotação inválida.')
    if type(value.get('width')) is not int or not 1<=value['width']<=12:raise ProtocolError('Espessura de anotação inválida.')
    points=value.get('points')
    if not isinstance(points,list) or not 2<=len(points)<=512:raise ProtocolError('Quantidade de pontos inválida.')
    for point in points:
        if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in point):raise ProtocolError('Coordenada de anotação inválida.')
    return dict(shape=value['shape'],color=value['color'],width=value['width'],points=[list(point) for point in points])

class RemoteFeatures:
    def __init__(self,peer):
        self.peer=peer;self.outgoing={};self.lock=threading.Lock();self.busy=False;self.last_request=0.
        self.whiteboard_allowed=False;self.viewer_whiteboard=False;self.last_stroke=0.;self.strokes=0;self.points=0

    def request(self,operation):
        if self.peer.role!='viewer' or operation not in CAPABILITIES:raise ValueError('Ação indisponível nesta ponta.')
        if operation not in self.peer.remote_capabilities:raise ValueError('Atualize o Desk nas duas máquinas para usar esta função.')
        if operation in ('restart','whiteboard') and not self.peer.permissions.get('control'):raise ValueError('O computador remoto precisa permitir mouse e teclado primeiro.')
        with self.lock:
            if self.outgoing:raise ValueError('Aguarde a resposta da solicitação anterior.')
            token=secrets.token_hex(8);self.outgoing[token]=(operation,time.monotonic())
        self.peer.send(dict(type='advanced_request',id=token,operation=operation));return token

    def handle(self,msg):
        kind=msg.get('type')
        if kind=='capabilities':
            values=msg.get('values')
            if not isinstance(values,list) or len(values)>16 or any(not isinstance(x,str) or len(x)>40 for x in values):raise ProtocolError('Capacidades inválidas.')
            self.peer.remote_capabilities=set(values)&CAPABILITIES;self.peer.event('capabilities',dict(values=sorted(self.peer.remote_capabilities)));return
        if kind=='advanced_request':
            token,operation=msg.get('id'),msg.get('operation')
            if not isinstance(token,str) or len(token)!=16 or any(c not in '0123456789abcdef' for c in token) or operation not in CAPABILITIES:raise ProtocolError('Solicitação avançada inválida.')
            if self.peer.role!='host':return
            with self.lock:
                if self.busy or time.monotonic()-self.last_request<1:
                    self.peer.send(dict(type='advanced_result',id=token,operation=operation,status='busy'));return
                self.busy=True;self.last_request=time.monotonic()
            self.peer.spawn(lambda:self._approve(token,operation));return
        if kind=='advanced_result':
            token=msg.get('id')
            with self.lock:item=self.outgoing.pop(token,None)
            if item is None or msg.get('operation')!=item[0]:return
            status=msg.get('status');values=msg.get('values',{})
            if status not in ('accepted','declined','busy','failed'):raise ProtocolError('Resposta avançada inválida.')
            if not isinstance(values,dict) or len(values)>8 or any(k not in INFO_FIELDS or not isinstance(v,str) or len(v)>200 for k,v in values.items()):raise ProtocolError('Informações técnicas inválidas.')
            if item[0]=='whiteboard' and status=='accepted':self.viewer_whiteboard=True
            self.peer.event('advanced_result',dict(id=token,operation=item[0],status=status,values=values));return
        if kind=='whiteboard_state':
            if self.peer.role=='viewer' and msg.get('enabled') is False:
                self.viewer_whiteboard=False;self.peer.event('whiteboard_disabled',{})
            return
        if kind=='annotation':
            if self.peer.role!='host' or not self.whiteboard_allowed or not self.peer.permissions.get('control'):return
            action=msg.get('action')
            if action=='clear':self.strokes=0;self.points=0;self.peer.event('annotation_clear',{});return
            if action=='disable':self.revoke();return
            if action!='stroke':raise ProtocolError('Ação de anotação inválida.')
            stroke=validate_stroke(msg.get('stroke'))
            if self.strokes>=100 or self.points+len(stroke['points'])>16000 or time.monotonic()-self.last_stroke<.03:return
            self.strokes+=1;self.points+=len(stroke['points']);self.last_stroke=time.monotonic();self.peer.event('annotation',dict(stroke=stroke,peer=self.peer))

    def _approve(self,token,operation):
        status='declined';values={}
        try:
            if self.peer.closed.is_set():return
            if operation in ('restart','whiteboard') and not self.peer.permissions.get('control'):return
            answer=self.peer.request('advanced_action',dict(operation=operation,id=token,_peer=self.peer,_cancelled=self.peer.closed.is_set),90)
            if self.peer.closed.is_set() or not answer:return
            if operation in ('restart','whiteboard') and not self.peer.permissions.get('control'):return
            if operation=='system_info':values=system_information(self.peer.monitors)
            elif operation=='print':
                from .printing import PRINT_SUFFIXES
                path=Path(str(answer))
                if path.suffix.lower() not in PRINT_SUFFIXES or not path.is_file():return
                self.peer.send_file(path)
            elif operation=='whiteboard':self.whiteboard_allowed=True
            status='accepted'
        except Exception:status='failed'
        finally:
            with self.lock:self.busy=False
            if not self.peer.closed.is_set():self.peer.send(dict(type='advanced_result',id=token,operation=operation,status=status,values=values))

    def send_stroke(self,stroke):
        if self.peer.role=='viewer' and self.viewer_whiteboard and self.peer.permissions.get('control'):
            self.peer.send(dict(type='annotation',action='stroke',stroke=validate_stroke(stroke)))

    def clear(self):
        if self.viewer_whiteboard:self.peer.send(dict(type='annotation',action='clear'))

    def revoke(self):
        self.whiteboard_allowed=False;self.viewer_whiteboard=False;self.strokes=0;self.points=0
        self.peer.event('annotation_clear',{})
        if not self.peer.closed.is_set() and self.peer.role=='host':self.peer.send(dict(type='whiteboard_state',enabled=False))

    def expire(self):
        with self.lock:expired=[(key,value) for key,value in self.outgoing.items() if time.monotonic()-value[1]>95]
        for token,(operation,_) in expired:
            with self.lock:self.outgoing.pop(token,None)
            self.peer.event('advanced_result',dict(id=token,operation=operation,status='failed',values={}))
