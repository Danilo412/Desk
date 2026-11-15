import sys
from PySide6.QtCore import Qt, QEvent, QAbstractAnimation
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow
from novoacesso import ui_motion


def test_button_feedback_preserves_mouse_keyboard_and_disabled_actions(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:True)
    calls=[];monkeypatch.setattr(MainWindow,'copy_invite',lambda self:calls.append('copy'))
    window=MainWindow();window.show();QTest.qWait(40)
    try:
        button=window.copy_address_button;effect=window.interface_motion.feedback[button]
        QTest.mousePress(button,Qt.MouseButton.LeftButton)
        assert effect.isVisible() and effect.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert effect.focusPolicy()==Qt.FocusPolicy.NoFocus
        assert button.childAt(button.rect().center()) is not effect
        assert calls==[]
        QTest.mouseRelease(button,Qt.MouseButton.LeftButton);assert calls==['copy']
        button.setFocus();QTest.keyClick(button,Qt.Key.Key_Space);assert calls==['copy','copy']
        button.setEnabled(False);QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        assert calls==['copy','copy'] and not effect.isVisible()
    finally:window.close();QTest.qWait(30)


def test_motion_preference_preserves_identity_and_respects_windows(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:True)
    window=MainWindow();address=window.identity.desk_address
    window.motion_enabled.setChecked(False)
    assert window.identity.settings()['interface_motion'] is False
    window.close();QTest.qWait(30)
    window=MainWindow()
    try:
        assert window.identity.desk_address==address and not window.interface_motion.enabled
        assert not window.motion_enabled.isChecked()
        monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:False)
        window.motion_enabled.setChecked(True)
        assert not window.interface_motion.enabled
    finally:window.close();QTest.qWait(30)


def test_dynamic_dialog_and_fast_navigation_have_no_late_callbacks(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:True)
    errors=[];monkeypatch.setattr(sys,'excepthook',lambda *e:errors.append(e))
    window=MainWindow();window.show();QTest.qWait(40);motion=window.interface_motion
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    button=QPushButton('Testar',dialog);layout=QVBoxLayout(dialog);layout.addWidget(button);dialog.show();QTest.qWait(30)
    assert button in motion.feedback
    QTest.mousePress(button,Qt.MouseButton.LeftButton);dialog.close();QTest.qWait(30)
    for page in (1,0,1,2,0,1):window.tabs.setCurrentIndex(page)
    window.resize(1050,700);QTest.qWait(220)
    assert motion.indicator.isVisible()
    assert motion.indicator.geometry().center().x()==window.session_nav.geometry().center().x()
    motion.set_requested(False)
    assert motion.nav_animation.state()==QAbstractAnimation.State.Stopped
    window.close();QTest.qWait(220)
    assert not errors
