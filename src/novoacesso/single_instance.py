"""Uma instância por perfil, com reabertura da janela por canal local."""
import hashlib,os
from pathlib import Path
from PySide6.QtCore import QLockFile,QTimer
from PySide6.QtNetwork import QLocalServer,QLocalSocket

class SingleInstance:
    def __init__(self,root=None):
        self.root=Path(root or os.environ.get('NOVOACESSO_STATE_DIR') or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'NovoAcesso').resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.name='Desk-'+hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:32]
        self.lock=QLockFile(str(self.root/'desk-instance.lock'));self.lock.setStaleLockTime(0)
        self.server=None;self.callback=None;self.sockets=[]
    def acquire(self,background=False):
        if not self.lock.tryLock(0):
            socket=QLocalSocket();socket.connectToServer(self.name)
            connected=socket.waitForConnected(600)
            if connected:
                socket.write(b'background' if background else b'show');socket.flush();socket.waitForBytesWritten(600)
                socket.waitForReadyRead(600)
                socket.disconnectFromServer()
                if socket.state()!=QLocalSocket.LocalSocketState.UnconnectedState:socket.waitForDisconnected(600)
            return False
        QLocalServer.removeServer(self.name)
        self.server=QLocalServer();self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(self.name):self.lock.unlock();raise RuntimeError('Não foi possível reservar a instância local do Desk.')
        self.server.newConnection.connect(self._incoming);return True
    def _incoming(self):
        while self.server and self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection();self.sockets.append(socket)
            socket.disconnected.connect(lambda current=socket:self._discard(current))
            socket.readyRead.connect(lambda current=socket:self._read(current))
            timer=QTimer(socket);timer.setSingleShot(True);timer.timeout.connect(socket.abort);timer.start(1500)
            if socket.bytesAvailable():self._read(socket)
    def _read(self,socket):
        data=bytes(socket.readAll())
        if data==b'show' and self.callback:self.callback()
        socket.write(b'ok');socket.flush()
    def _discard(self,socket):
        if socket in self.sockets:self.sockets.remove(socket)
        socket.deleteLater()
    def close(self):
        for socket in list(self.sockets):socket.abort();socket.deleteLater()
        self.sockets.clear()
        if self.server:self.server.close();self.server=None;self.lock.unlock()
