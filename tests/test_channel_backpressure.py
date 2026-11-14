import queue
import threading
import time
from novoacesso import wire

class IdleSocket:
    def settimeout(self,value):pass
    def setblocking(self,value):pass
    def close(self):pass

def test_full_incoming_queue_waits_without_empty_windows_select(monkeypatch):
    channel=wire.Channel(IdleSocket());calls=[]
    for i in range(channel.incoming.maxsize):channel.incoming.put((b'J',b'{}'))
    def windows_select(reads,writes,errors,timeout):
        calls.append((reads,writes))
        if not reads and not writes:raise OSError(10022,'Windows select requires a socket')
        raise AssertionError('A full receive queue with no outgoing data needs no socket I/O')
    monkeypatch.setattr(wire.select,'select',windows_select)
    worker=threading.Thread(target=channel._pump,daemon=True);worker.start()
    try:
        time.sleep(.05)
        assert worker.is_alive() and not channel.closed.is_set(),channel.failure
        assert calls==[]
    finally:channel.closed.set();worker.join(2)
