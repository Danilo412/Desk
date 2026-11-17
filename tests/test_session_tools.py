import threading
from types import SimpleNamespace
from PIL import Image
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow

def viewer_peer(messages):
    return SimpleNamespace(role='viewer',permissions=dict(control=False,clipboard=False,audio=False),closed=threading.Event(),
                           channel=SimpleNamespace(sock=SimpleNamespace(version=lambda:'TLSv1.3',outer=SimpleNamespace(route_info='WebRTC: relay'))),send=messages.append)

def test_monitor_menu_routes_to_selected_monitor_without_granting_control(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();messages=[];window.peer=viewer_peer(messages)
    try:
        monitors=[dict(left=0,top=0,width=1920,height=1080)]*3
        window.on_event('connected',dict(role='viewer',permissions=window.peer.permissions,monitors=monitors))
        menu=window.monitor_picker.menu();window.populate_monitor_menu(menu)
        action=next(a for a in menu.actions() if a.data()==2);action.trigger()
        assert window.monitor.currentData()==2 and messages[-1]['monitor']==2
        assert window.monitor_picker.text()=='Monitor 2' and window.fullscreen_tools.monitors.text()=='Monitor 2'
        assert not window.canvas.allow_control and not window.control.isChecked()
    finally:window.peer=None;window.close();QTest.qWait(20)

def test_information_updates_on_permission_change_and_disconnection(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.peer=viewer_peer([])
    window.canvas.set_frame(Image.new('RGB',(1920,1080),'navy'))
    dialog=window.build_session_information_window()
    try:
        dialog.show();QTest.qWait(20);values=dialog.information_labels
        assert values['Proteção'].text()=='TLSv1.3' and values['Tela recebida'].text()=='1920 × 1080'
        assert values['Mouse e teclado'].text()=='Não permitido'
        window.peer.permissions['audio']=True;QTest.qWait(600)
        assert values['Áudio'].text()=='Permitido' and not window.canvas.allow_control
        window.peer.role='host';window.peer.width=2560;window.peer.fps=60;QTest.qWait(600)
        assert values['Qualidade solicitada'].text()=='2560 px / 60 FPS'
        assert values['Exibição'].text()=='Configurada pela outra ponta'
        window.peer.closed.set();QTest.qWait(600)
        assert values['Estado'].text()=='Sem sessão ativa' and values['Proteção'].text()=='—'
    finally:dialog.close();window.peer=None;window.close();QTest.qWait(20)


def test_information_rows_remain_available_before_first_metrics(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.peer=viewer_peer([])
    dialog=window.build_session_information_window()
    try:
        dialog.show();QTest.qWait(20)
        window.peer.receive_metrics=dict(received_fps=30,received_kbps=1200,decode_ms=6)
        window._last_stream_stats=dict(capture='MSS',capture_ms=115,encode_ms=12,delivery_ms=145,pending_frames=2,pending_kib=64,input_apply_ms=90,input_fast=1)
        QTest.qWait(600)
        values=dialog.information_labels
        assert 'captura 115.0 ms' in values['Captura e codificação'].text()
        assert 'codificação 12.0 ms' in values['Captura e codificação'].text()
        assert 'Canal dedicado' in values['Controle remoto'].text()
        assert '30.0 FPS' in values['Fluxo recebido'].text()
        assert '145.0 ms' in values['Entrega do quadro'].text()
    finally:dialog.close();window.peer=None;window.close();QTest.qWait(20)

def test_fullscreen_image_menu_and_pin_preserve_escape(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.peer=viewer_peer([]);window.update_session_actions();window.show()
    try:
        window.fullscreen();QTest.qWait(60)
        assert window.fullscreen_tools.image.menu() is window.image_menu_button.menu()
        opened=[]
        def use_fullscreen_image_menu():
            menu=window.fullscreen_tools.image.menu();opened.append(menu.isVisible())
            window.display.setCurrentIndex(window.display.findData('stretch'));menu.close()
        QTimer.singleShot(30,use_fullscreen_image_menu);window.fullscreen_tools.image.showMenu()
        assert opened==[True] and window.canvas.display_mode=='stretch'
        assert window.identity.settings()['view']['display']=='stretch'
        window.fullscreen_tools.pin.setChecked(True);window.fullscreen_tools.hide_if_unused()
        assert window.fullscreen_tools.isVisible() and window.identity.settings()['desk_fullscreen_bar_pinned'] is True
        QTest.keyClick(window.canvas,Qt.Key.Key_Escape);QTest.qWait(40)
        assert not window._fullscreen and window.viewer.parent() is window.session_split and window.fullscreen_tools.isHidden()
    finally:window.peer=None;window.close();QTest.qWait(20)
