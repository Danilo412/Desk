"""Compact Desk title strip with native Windows move/resize behavior."""
import os
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QFrame,QToolButton


class DeskTitleStrip(QFrame):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setObjectName('titleStrip')
        owner.installEventFilter(self);self.maximize_button=None

    def add_window_controls(self,row):
        for text,label,callback in [('−','Minimizar',self.owner.showMinimized),('□','Maximizar',self.toggle_maximize),('×','Fechar',self.owner.close)]:
            button=QToolButton(self);button.setText(text);button.setAccessibleName(label);button.setToolTip(label)
            button.setObjectName('windowClose' if label=='Fechar' else 'windowControl');button.setFixedSize(38,30)
            button.clicked.connect(callback);row.addWidget(button)
            if label=='Maximizar':self.maximize_button=button

    def toggle_maximize(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.WindowStateChange and self.maximize_button:
            label='Restaurar' if self.owner.isMaximized() else 'Maximizar'
            self.maximize_button.setText('▣' if self.owner.isMaximized() else '□');self.maximize_button.setToolTip(label);self.maximize_button.setAccessibleName(label)
        return False

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove();event.accept();return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.toggle_maximize();event.accept();return
        super().mouseDoubleClickEvent(event)


def frame_hit_test(window,message):
    if os.name!='nt' or window.isMaximized() or window.isFullScreen():return None
    import ctypes
    from ctypes import wintypes
    msg=ctypes.cast(int(message),ctypes.POINTER(wintypes.MSG)).contents
    if msg.message!=0x84:return None  # WM_NCHITTEST
    bounds=wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(window.winId())),ctypes.byref(bounds)):return None
    x=ctypes.c_short(msg.lParam & 0xffff).value;y=ctypes.c_short((msg.lParam >> 16) & 0xffff).value
    border=max(5,round(6*window.devicePixelRatioF()))
    left=bounds.left<=x<bounds.left+border;right=bounds.right-border<=x<bounds.right
    top=bounds.top<=y<bounds.top+border;bottom=bounds.bottom-border<=y<bounds.bottom
    if top:return 13 if left else 14 if right else 12
    if bottom:return 16 if left else 17 if right else 15
    return 10 if left else 11 if right else None
