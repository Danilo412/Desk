import threading
from types import SimpleNamespace
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from novoacesso.app import MainWindow,Prompt
from novoacesso.quality import preferences
from novoacesso.saved_connections import save_address,list_connections

def peer(messages):
    return SimpleNamespace(role='viewer',permissions=dict(control=False,clipboard=False,audio=False),closed=threading.Event(),send=messages.append)

def test_image_presets_sync_and_preserve_monitor_codec_and_saved_settings(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();messages=[];window.peer=peer(messages)
    try:
        for i in range(3):window.monitor.addItem('Monitor '+str(i),i)
        window.monitor.setCurrentIndex(2);window.codec.setCurrentIndex(window.codec.findData('deflate'))
        id=save_address(window.identity,'PC teste','1234 1234 1234');window.active_saved_id=id
        window._image_panels[0].buttons['quality'].click()
        assert window.quality.currentData()==(2560,30) and window.monitor.currentData()==2 and window.codec.currentData()=='deflate'
        assert messages[-1]['width']==2560 and messages[-1]['monitor']==2 and messages[-1]['fps']==30
        assert all(p.buttons['quality'].isChecked() for p in window._image_panels)
        panel=window._image_panels[1];panel.advanced_toggle.setChecked(True);panel.quality.setCurrentIndex(3);panel.start_fullscreen.setChecked(True)
        assert window.quality.currentData()==(2560,60) and all(p.custom.isChecked() for p in window._image_panels)
        view=next(e for e in list_connections(window.identity) if e['id']==id)['view']
        assert view['start_fullscreen'] is True and view['width']==2560 and view['fps']==60 and view['codec']=='deflate'
    finally:window.peer=None;window.close();QTest.qWait(20)

def test_preferred_fullscreen_escape_and_minimize_keep_session(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.show();window.peer=peer([]);session=window.peer
    try:
        window.start_fullscreen.setChecked(True)
        window.on_event('connected',dict(role='viewer',permissions=session.permissions,monitors=[dict(left=0,top=0,width=1920,height=1080)]*2));QTest.qWait(60)
        assert window._fullscreen
        QTest.keyClick(window.canvas,Qt.Key.Key_Escape);QTest.qWait(30)
        assert not window._fullscreen and window.viewer.parent() is window.session_split
        window.begin_preferred_fullscreen(window.connection_epoch-1);assert not window._fullscreen
        window.fullscreen();window.fullscreen_tools.minimize.click();QTest.qWait(30)
        assert window.isMinimized() and not window._fullscreen and window.peer is session and not session.closed.is_set()
        window.showNormal();QTest.qWait(20);assert not window.canvas.allow_control
    finally:window.peer=None;window.close();QTest.qWait(20)

def test_old_preferences_keep_the_same_shape_and_default_quality(tmp_path,monkeypatch):
    legacy=dict(width=2560,fps=60,codec='deflate',auto_reconnect=True,display='fit')
    assert preferences(legacy)==legacy and preferences(dict(legacy,start_fullscreen=True))['start_fullscreen'] is True
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        assert window.quality.currentData()==(1920,30) and not window.start_fullscreen.isChecked()
        window.apply_view_preferences(legacy)
        assert window.quality.currentData()==(2560,60) and window.codec.currentData()=='deflate'
        assert all(p.custom.isChecked() for p in window._image_panels)
        assert window.settings_navigation.item(3).text()=='Imagem'
    finally:window.close();QTest.qWait(20)

def test_fullscreen_image_actions_and_file_dialog_use_current_window(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.show();window.peer=peer([]);window.update_session_actions()
    cancelled=threading.Event();observed=[]
    try:
        window.fullscreen();QTest.qWait(40)
        def select_quality():
            assert window.image_menu_button.menu().isVisible()
            window._image_panels[0].buttons['quality'].click();window.image_menu_button.menu().close()
        QTimer.singleShot(40,select_quality);window.fullscreen_tools.image.showMenu()
        assert window.quality.currentData()==(2560,30) and window._fullscreen
        def cancel_destination():
            observed.append(QApplication.activeModalWidget().parent() is window.fullscreen_window);cancelled.set()
        QTimer.singleShot(40,cancel_destination)
        window.on_prompt(Prompt('save_file',dict(name='not-written.bin',size=1,_cancelled=cancelled.is_set)))
        assert observed==[True] and window._fullscreen
        window.fullscreen_tools.actions.menu().actions()[0].trigger();QTest.qWait(30)
        assert not window._fullscreen and window.session_side.currentIndex()==0
    finally:window.peer=None;window.close();QTest.qWait(20)
