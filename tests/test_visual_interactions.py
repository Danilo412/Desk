import sys
from PySide6.QtCore import Qt,QAbstractAnimation
from PySide6.QtWidgets import QToolButton,QApplication
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow
from novoacesso import ui_motion


def test_whole_shortcut_card_is_one_keyboard_and_mouse_action(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));calls=[]
    monkeypatch.setattr(MainWindow,'copy_invite',lambda self:calls.append('copy'))
    window=MainWindow();window.show();QTest.qWait(50)
    try:
        card=window.quick_tiles.tiles[0]
        QTest.mouseClick(card,Qt.MouseButton.LeftButton,pos=card.rect().center());assert calls==['copy']
        card.setFocus();QTest.keyClick(card,Qt.Key.Key_Space);assert calls==['copy','copy']
        assert card.height()>=card.layout().minimumSize().height()
        assert window.permissions()==dict(control=False,clipboard=False,audio=False)
    finally:window.close();QTest.qWait(30)


def test_advanced_box_reverse_and_reduced_motion_leave_no_hidden_state(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:True)
    window=MainWindow();window.show();window.tabs.setCurrentIndex(2);window.settings_navigation.setCurrentRow(3)
    panel=window._image_panels[1]
    try:
        for checked in (True,False,True):panel.advanced_toggle.setChecked(checked);QTest.qWait(20)
        window.motion_enabled.setChecked(False);QTest.qWait(200)
        assert panel.advanced.isVisible() and panel.advanced.maximumHeight()==16777215
        panel.advanced_toggle.setChecked(False)
        assert panel.advanced.isHidden()
        assert window.quality.currentData()==(1920,30) and not window.canvas.allow_control
    finally:window.close();QTest.qWait(30)


def test_fullscreen_slide_stops_on_escape_and_window_controls_restore(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));monkeypatch.setattr(ui_motion,'system_allows_motion',lambda:True)
    errors=[];monkeypatch.setattr(sys,'excepthook',lambda *e:errors.append(e))
    window=MainWindow();window.show();QTest.qWait(30)
    try:
        maximize=next(b for b in window.findChildren(QToolButton) if b.accessibleName()=='Maximizar')
        maximize.click();QTest.qWait(30);assert window.isMaximized()
        maximize.click();QTest.qWait(30);assert not window.isMaximized()
        window.fullscreen();QTest.qWait(25);bar=window.fullscreen_tools
        monkeypatch.setattr(bar,'underMouse',lambda:False)
        bar.hide_if_unused();QTest.qWait(25);bar.reveal();QTest.qWait(25)
        QTest.keyClick(window.canvas,Qt.Key.Key_Escape);QTest.qWait(240)
        assert not window._fullscreen and bar.isHidden() and window.viewer.parent() is window.session_split
        assert bar.slide.state()==QAbstractAnimation.State.Stopped and not errors
    finally:window.close();QTest.qWait(30)


def test_settings_navigation_icons_and_session_capture_button(tmp_path,monkeypatch):
    import threading
    from types import SimpleNamespace
    from PIL import Image
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path))
    window=MainWindow();window.show();QTest.qWait(30)
    try:
        assert window.settings_navigation.count()==7
        for i in range(window.settings_navigation.count()):
            assert not window.settings_navigation.item(i).icon().isNull()
        assert window.update_banner.isHidden()
        assert not window.session_screenshot_button.isEnabled()
        window.peer=SimpleNamespace(role='viewer',permissions=dict(control=False,audio=False,clipboard=False),closed=threading.Event(),remote_capabilities=set())
        window.canvas.set_frame(Image.new('RGB',(320,180),'navy'))
        window.update_session_actions()
        assert window.session_screenshot_button.isEnabled()
    finally:
        window.peer=None;window.close();QTest.qWait(30)
