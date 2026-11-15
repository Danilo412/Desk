"""Janela própria de tela cheia, sem moldura nem geometria da área útil."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

class RemoteFullscreenWindow(QWidget):
    def __init__(self,owner):
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.owner=owner;self.setWindowIcon(owner.windowIcon())
    def closeEvent(self,event):
        event.ignore();self.owner.exit_fullscreen()
