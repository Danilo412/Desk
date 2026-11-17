"""Keep the UI responsive while preserving button/key order under backpressure."""
from collections import deque
import threading

class InputDispatcher:
    def __init__(self,send,closed,allowed,failed):
        self.send=send;self.closed=closed;self.allowed=allowed;self.failed=failed
        self.queue=deque();self.condition=threading.Condition();self.thread=None
    def put(self,value):
        with self.condition:
            if self.closed.is_set():return
            value=dict(value)
            if value.get('event')=='move' and self.queue and self.queue[-1].get('event')=='move':self.queue[-1]=value
            elif len(self.queue)<128:self.queue.append(value)
            else:
                self.failed('O controle não acompanhou a conexão. Reconecte para continuar.');return
            if self.thread is None:
                self.thread=threading.Thread(target=self.run,daemon=True,name='Desk input');self.thread.start()
            self.condition.notify()
    def run(self):
        while not self.closed.is_set():
            with self.condition:
                while not self.queue and not self.closed.is_set():self.condition.wait(.1)
                if self.closed.is_set():return
                value=self.queue.popleft()
            if self.allowed() or value.get('event')=='release':self.send(dict(value,type='input'))
    def stop(self):
        with self.condition:self.queue.clear();self.condition.notify_all()
