"""Small, local UI transitions. Native button signals remain authoritative."""
import os
import sys
import weakref
import json,time

from PySide6.QtCore import QObject, QEvent, Qt, QTimer, QVariantAnimation, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QPushButton, QToolButton, QFrame,QLayout
from shiboken6 import isValid


def system_allows_motion():
    if os.environ.get('DESK_REDUCED_MOTION') == '1':
        return False
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        enabled = wintypes.BOOL(True)
        # Read the Windows accessibility preference; never change it.
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    return True


class RevealAnimation(QObject):
    """Expand a settings box, clipping its own contents only."""
    def __init__(self, widget, owner):
        super().__init__(widget);self.widget=widget;self.owner=owner;self.expanded=not widget.isHidden()
        self._constraint=widget.layout().sizeConstraint() if widget.layout() else None
        self._minimum_height=widget.minimumHeight();self._samples=[];self._started=None
        self.animation=QPropertyAnimation(widget,b'maximumHeight',self)
        self.animation.setDuration(260);self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.sample)
        self.animation.finished.connect(self.finish_motion)
        if hasattr(owner,'interface_motion'):owner.interface_motion.transitions.add(self)

    def set_expanded(self, expanded):
        widget=self.widget;self.expanded=bool(expanded);self.animation.stop()
        self._samples=[];self._started=time.monotonic()
        motion=getattr(self.owner,'interface_motion',None)
        self.trace('request',motion_enabled=bool(motion and motion.enabled),owner_visible=self.owner.isVisible(),expanded=self.expanded)
        if not motion or not motion.enabled or not self.owner.isVisible():
            self.finish_motion();return
        current=0 if widget.isHidden() else widget.height()
        natural=max(1,widget.layout().sizeHint().height()) if widget.layout() else widget.sizeHint().height()
        if widget.layout():widget.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        widget.setMinimumHeight(0)
        widget.setMaximumHeight(current);widget.setVisible(True)
        self.animation.setStartValue(current);self.animation.setEndValue(natural if expanded else 0);self.animation.start()

    def finish_motion(self):
        self.animation.stop();self.widget.setVisible(self.expanded);self.widget.setMaximumHeight(16777215)
        self.widget.setMinimumHeight(self._minimum_height)
        if self.widget.layout() and self._constraint is not None:self.widget.layout().setSizeConstraint(self._constraint)
        self.trace('settled',expanded=self.expanded,elapsed_ms=round((time.monotonic()-self._started)*1000) if self._started else None,samples=self._samples)

    def sample(self,value):
        if os.environ.get('DESK_UI_TRACE_PATH'):
            self._samples.append(dict(value=int(value),height=self.widget.height(),minimum=self.widget.minimumHeight()))

    def trace(self,phase,**fields):
        path=os.environ.get('DESK_UI_TRACE_PATH')
        if not path:return
        try:
            with open(path,'a',encoding='utf-8') as output:output.write(json.dumps(dict(component='advanced_box',phase=phase,**fields))+'\n')
        except OSError:pass


def reveal_widget(widget, expanded, owner):
    transition=getattr(widget,'_desk_reveal',None)
    if transition is None:
        transition=widget._desk_reveal=RevealAnimation(widget,owner)
    transition.set_expanded(expanded)


class ButtonFeedback(QWidget):
    """Paint-only child: no focus, hit testing, resizing or delayed actions."""
    def __init__(self, button, controller):
        super().__init__(button)
        self.controller = controller
        self.level = 0.0
        self.setObjectName('buttonFeedback')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.set_level)
        button.pressed.connect(self.pressed)
        button.released.connect(self.released)
        self.hide()

    def set_level(self, value):
        self.level = float(value)
        if self.level <= .001:
            self.hide()
        else:
            self.show()
            self.raise_()
            self.update()

    def animate_to(self, level, duration=130):
        button = self.parentWidget()
        if not self.controller.enabled or not button.isEnabled() or not button.isVisible():
            self.reset()
            return
        self.setGeometry(button.rect())
        self.animation.stop()
        self.animation.setDuration(duration)
        self.animation.setStartValue(self.level)
        self.animation.setEndValue(float(level))
        self.animation.start()

    def pressed(self):
        if self.controller.enabled and self.parentWidget().isEnabled():
            self.animation.stop()
            self.setGeometry(self.parentWidget().rect())
            self.set_level(.11)

    def released(self):
        self.animate_to(.035 if self.parentWidget().underMouse() else 0, 160)

    def reset(self):
        self.animation.stop()
        self.set_level(0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor('#ffffff')
        color.setAlphaF(min(.12, max(0, self.level)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)


class InterfaceMotion(QObject):
    def __init__(self, window, requested=True):
        super().__init__(window)
        self.window = window
        self.requested = bool(requested)
        self.enabled = self.requested and system_allows_motion()
        self.watched = weakref.WeakSet()
        self.feedback = weakref.WeakKeyDictionary()
        self.transitions = weakref.WeakSet()
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.scan)
        self.nav_timer = QTimer(self)
        self.nav_timer.setSingleShot(True)
        self.nav_timer.timeout.connect(lambda: self.select_page(self.window.tabs.currentIndex(), False))
        self.indicator = QFrame(window.home_nav.parentWidget())
        self.indicator.setObjectName('navigationIndicator')
        self.indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.indicator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav_animation = QVariantAnimation(self)
        self.nav_animation.setDuration(150)
        self.nav_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.nav_animation.valueChanged.connect(self.indicator.setGeometry)
        self.scan()
        self.select_page(window.tabs.currentIndex(), False)

    def scan(self):
        for widget in [self.window, *self.window.findChildren(QWidget)]:
            if isinstance(widget, ButtonFeedback) or widget in self.watched:
                continue
            self.watched.add(widget)
            widget.installEventFilter(self)
            if hasattr(widget,'finish_motion'):self.transitions.add(widget)
            if isinstance(widget, (QPushButton, QToolButton)):
                self.feedback[widget] = ButtonFeedback(widget, self)

    def set_requested(self, requested):
        self.requested = bool(requested)
        self.enabled = self.requested and system_allows_motion()
        if not self.enabled:
            self.stop()

    def stop(self):
        self.nav_animation.stop()
        for transition in list(self.transitions):
            if isValid(transition):transition.finish_motion()
        for feedback in list(self.feedback.values()):
            if isValid(feedback):
                feedback.reset()
        self.select_page(self.window.tabs.currentIndex(), False)

    def select_page(self, index, animate=True):
        self.nav_animation.stop()
        if index not in (0, 1):
            self.indicator.hide()
            return
        button = (self.window.home_nav, self.window.session_nav)[index]
        target = button.geometry().adjusted(10, 0, -10, 0)
        target.setTop(target.bottom()-1)
        if animate and self.enabled and self.indicator.isVisible():
            self.nav_animation.setStartValue(self.indicator.geometry())
            self.nav_animation.setEndValue(target)
            self.nav_animation.start()
        else:
            self.indicator.setGeometry(target)
        self.indicator.show()
        self.indicator.raise_()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QEvent.Type.ChildAdded, QEvent.Type.ChildPolished):
            if not self.scan_timer.isActive():
                self.scan_timer.start(0)
        if obj is self.window:
            if kind == QEvent.Type.Hide:
                self.stop()
            elif kind == QEvent.Type.ActivationChange:
                self.set_requested(self.requested)
        if obj in (self.window.home_nav, self.window.session_nav) and kind in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self.nav_timer.start(0)
        feedback = self.feedback.get(obj)
        if feedback is not None and isValid(feedback):
            if kind == QEvent.Type.Enter:
                feedback.animate_to(.035)
            elif kind == QEvent.Type.Leave:
                feedback.animate_to(0)
            elif kind in (QEvent.Type.Hide, QEvent.Type.EnabledChange):
                feedback.reset()
            elif kind == QEvent.Type.Resize:
                feedback.setGeometry(obj.rect())
        return False
