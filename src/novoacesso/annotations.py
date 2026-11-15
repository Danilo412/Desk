"""Normalized annotation drawing shared by the viewer and approved host overlay."""
import math,os
from PySide6.QtCore import Qt,QRectF,QPointF,QRect
from PySide6.QtGui import QPainter,QColor,QPen,QPolygonF
from PySide6.QtWidgets import QWidget,QApplication

def paint_stroke(painter,rect,stroke):
    points=[QPointF(rect.x()+x*rect.width(),rect.y()+y*rect.height()) for x,y in stroke['points']]
    if len(points)<2:return
    painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen=QPen(QColor(stroke['color']),stroke['width']);pen.setCapStyle(Qt.PenCapStyle.RoundCap);pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen);painter.setBrush(Qt.BrushStyle.NoBrush);a,b=points[0],points[-1];shape=stroke['shape']
    if shape=='freehand':painter.drawPolyline(QPolygonF(points))
    elif shape in ('line','arrow'):
        painter.drawLine(a,b)
        if shape=='arrow':
            angle=math.atan2(b.y()-a.y(),b.x()-a.x());length=12+stroke['width']
            for side in (-1,1):painter.drawLine(b,QPointF(b.x()-length*math.cos(angle+side*.45),b.y()-length*math.sin(angle+side*.45)))
    elif shape=='rectangle':painter.drawRect(QRectF(a,b).normalized())
    elif shape=='ellipse':painter.drawEllipse(QRectF(a,b).normalized())
    painter.restore()

def monitor_geometry(rect):
    if os.environ.get('QT_QPA_PLATFORM')=='offscreen' or os.name!='nt':return QRect(rect['left'],rect['top'],rect['width'],rect['height'])
    import ctypes
    from ctypes import wintypes
    class Info(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
    user=ctypes.windll.user32;user.MonitorFromRect.restype=wintypes.HANDLE
    bounds=wintypes.RECT(rect['left'],rect['top'],rect['left']+rect['width'],rect['top']+rect['height'])
    handle=user.MonitorFromRect(ctypes.byref(bounds),2);info=Info();info.size=ctypes.sizeof(info)
    if handle and user.GetMonitorInfoW(wintypes.HANDLE(handle),ctypes.byref(info)):
        if (bounds.left,bounds.top,bounds.right,bounds.bottom)!=(info.monitor.left,info.monitor.top,info.monitor.right,info.monitor.bottom):raise RuntimeError('Selecione um monitor individual para mostrar anotações nesta ponta.')
        for screen in QApplication.screens():
            if screen.name().casefold()==info.device.casefold():return screen.geometry()
    raise RuntimeError('Não foi possível alinhar as anotações ao monitor selecionado.')

class AnnotationOverlay(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput)
        self.setWindowTitle('Desk · Anotações autorizadas');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus);self.strokes=[]
    def add_stroke(self,stroke,rect):
        if len(self.strokes)>=100 or sum(len(s['points']) for s in self.strokes)+len(stroke['points'])>16000:return
        self.setGeometry(monitor_geometry(rect));self.strokes.append(stroke);self.show();self.update()
    def clear(self):self.strokes.clear();self.hide()
    def paintEvent(self,event):
        painter=QPainter(self)
        for stroke in self.strokes:paint_stroke(painter,QRectF(self.rect()),stroke)
