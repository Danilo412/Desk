"""Fragmentação limitada e escalonamento de controle, vídeo e arquivos."""
from collections import deque
import json,queue,struct,threading,time

FRAGMENT=16384
META=struct.Struct('>BcIII')  # lane, original kind, message id, total bytes, offset
LIMITS=(32,2,4,8)

def lane_for(kind,payload):
    if kind in (b'V',b'W'):return 1
    if kind==b'F':return 2
    if kind==b'A':return 3
    if kind==b'J':
        try:
            if json.loads(payload).get('type','').startswith('file_'):return 2
        except (ValueError,AttributeError):pass
    return 0

class Outgoing:
    def __init__(self):
        self.queues=[deque() for _ in LIMITS];self.active=[None]*4
        self.condition=threading.Condition();self.next_id=0;self.bulk_index=0;self.control_burst=0
        self.bytes_sent=0
        self.closed=False
    def put(self,record,timeout=2):
        kind=record[:1];payload=record[5:];lane=lane_for(kind,payload);deadline=time.monotonic()+timeout
        with self.condition:
            if self.closed:raise ConnectionError('Conexão encerrada.')
            while len(self.queues[lane])+int(self.active[lane] is not None)>=LIMITS[lane]:
                if self.closed:raise ConnectionError('Conexão encerrada.')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise queue.Full()
                self.condition.wait(min(.1,remaining))
            self.next_id=(self.next_id+1)&0xffffffff
            self.queues[lane].append((self.next_id,kind,payload));self.condition.notify_all()
    def qsize(self):
        with self.condition:return sum(len(q) for q in self.queues)+sum(a is not None for a in self.active)
    def video_pending(self):
        with self.condition:return len(self.queues[1])+int(self.active[1] is not None)
    def get_nowait(self):
        with self.condition:
            ready=[bool(self.queues[i] or self.active[i]) for i in range(4)]
            if not any(ready):raise queue.Empty()
            if ready[0] and (self.control_burst<8 or not any(ready[1:])):
                lane=0;self.control_burst+=1
            else:
                cycle=(3,1,1,2)
                lane=None
                for _ in cycle:
                    candidate=cycle[self.bulk_index%len(cycle)];self.bulk_index+=1
                    if ready[candidate]:lane=candidate;break
                if lane is None:lane=0
                self.control_burst=0
            if self.active[lane] is None:
                id,kind,payload=self.queues[lane].popleft();self.active[lane]=[id,kind,payload,0]
            id,kind,payload,offset=self.active[lane]
            data=payload[offset:offset+FRAGMENT];body=META.pack(lane,kind,id,len(payload),offset)+data
            offset+=len(data)
            if offset>=len(payload):self.active[lane]=None;self.condition.notify_all()
            else:self.active[lane][3]=offset
            self.bytes_sent+=len(body)+5
            return b'M'+struct.pack('>I',len(body))+body

    def close(self):
        with self.condition:
            self.closed=True
            for q in self.queues:q.clear()
            self.active=[None]*4;self.condition.notify_all()

class Incoming:
    def __init__(self,maximum,control_maximum,error):self.active={};self.maximum=maximum;self.control_maximum=control_maximum;self.error=error
    def feed(self,payload):
        if not META.size<=len(payload)<=META.size+FRAGMENT:raise self.error('Fragmento multiplexado inválido.')
        lane,kind,id,total,offset=META.unpack_from(payload);data=payload[META.size:]
        if lane>3 or kind not in (b'J',b'V',b'W',b'F',b'A') or total>self.maximum or (kind==b'J' and total>self.control_maximum):raise self.error('Canal multiplexado fora dos limites.')
        if (kind in (b'V',b'W') and lane!=1) or (kind==b'F' and lane!=2) or (kind==b'A' and lane!=3) or (kind==b'J' and lane not in (0,2)):raise self.error('Tipo inválido para o canal.')
        if offset==0:
            if lane in self.active:raise self.error('Mensagem sobreposta no canal.')
            self.active[lane]=(id,kind,total,bytearray())
        state=self.active.get(lane)
        if state is None or state[:3]!=(id,kind,total) or offset!=len(state[3]) or offset+len(data)>total or (not data and total):raise self.error('Sequência de fragmentos inválida.')
        state[3].extend(data)
        if len(state[3])==total:
            del self.active[lane];return kind,bytes(state[3])
        return None
