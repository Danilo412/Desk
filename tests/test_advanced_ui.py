import threading,time
from types import SimpleNamespace
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow,Prompt

def peer(role='viewer',control=True):
    return SimpleNamespace(role=role,permissions=dict(control=control,audio=False,clipboard=False),closed=threading.Event(),remote_capabilities={'restart','system_info','print','whiteboard'},
                           features=SimpleNamespace(viewer_whiteboard=False,clear=lambda:None),send=lambda *a:None,recording_audio_sink=None)

def test_screenshot_contains_annotations_and_chat_export_is_plain_text(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'state'));window=MainWindow();window.peer=peer();window.canvas.set_frame(Image.new('RGB',(320,180),'navy'))
    window.canvas.annotations=[dict(shape='line',color='#ef443b',width=8,points=[[.1,.5],[.9,.5]])]
    destinations=iter([tmp_path/'captura.png',tmp_path/'conversa.txt',tmp_path/'sessao.txt'])
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(next(destinations)),''))
    try:
        window.save_screenshot();image=Image.open(tmp_path/'captura.png');assert image.size==(320,180) and image.getpixel((160,90))[0]>150
        window.chat.appendPlainText('Você: <script>texto literal</script>');window.export_chat()
        assert '<script>texto literal</script>' in (tmp_path/'conversa.txt').read_text(encoding='utf-8')
        window.permanent_profile.setPlainText('NAU1-private-profile');window.export_session_report()
        report=(tmp_path/'sessao.txt').read_text(encoding='utf-8');assert 'NAU1-' not in report and 'NAR1-' not in report
    finally:window.peer=None;window.close();QTest.qWait(30)

def test_annotations_do_not_send_mouse_or_keyboard_input(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.tabs.setCurrentIndex(1);window.show();window.canvas.set_frame(Image.new('RGB',(640,360),'navy'));window.show_connection_state('active');QTest.qWait(40)
    events=[];strokes=[];window.canvas.allow_control=True;window.canvas.input_event.connect(events.append);window.canvas.stroke_finished.connect(strokes.append)
    try:
        window.canvas.set_annotation_mode(True);events.clear();rect=window.canvas.rect
        QTest.mousePress(window.canvas,Qt.MouseButton.LeftButton,pos=QPoint(int(rect.center().x()-30),int(rect.center().y())))
        QTest.mouseMove(window.canvas,QPoint(int(rect.center().x()+30),int(rect.center().y())))
        QTest.mouseRelease(window.canvas,Qt.MouseButton.LeftButton,pos=QPoint(int(rect.center().x()+30),int(rect.center().y())))
        assert len(strokes)==1 and not events
        QTest.keyClick(window.canvas,Qt.Key.Key_Escape);assert not window.canvas.annotation_mode
    finally:window.close();QTest.qWait(30)

def test_advanced_prompt_enter_declines_and_closed_session_cannot_restart(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.peer=peer('host');current=window.peer
    try:
        QTimer.singleShot(40,lambda:QTest.keyClick(QApplication.activeModalWidget(),Qt.Key.Key_Return))
        result=window.advanced_prompt(Prompt('advanced_action',dict(operation='restart',id='a'*16,_peer=current)))
        assert result is False and window.pending_restart is None
        current.closed.set();assert not window.schedule_remote_restart(current)
    finally:window.peer=None;window.close();QTest.qWait(30)

def test_restart_countdown_cancels_on_disconnect_and_command_is_only_called_at_deadline(tmp_path,monkeypatch):
    from novoacesso import advanced_ui
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));calls=[];monkeypatch.setattr(advanced_ui,'perform_restart',lambda:calls.append('restart'))
    window=MainWindow();window.peer=peer('host');current=window.peer
    try:
        assert window.schedule_remote_restart(current);job=window.pending_restart
        current.closed.set();job['timer'].timeout.emit();assert window.pending_restart is None and calls==[]
        current.closed.clear();assert window.schedule_remote_restart(current);job=window.pending_restart
        job['deadline']=time.monotonic()-1;job['timer'].timeout.emit();assert calls==['restart'] and window.pending_restart is None
    finally:window.peer=None;window.close();QTest.qWait(30)

def test_remote_recording_stops_and_finalizes_on_disconnection(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'state'));window=MainWindow();window.peer=peer();window.canvas.set_frame(Image.new('RGB',(320,180),'navy'))
    window._desk_listening_requested=False
    try:
        window.begin_recording(tmp_path/'sessao.mp4','remote');recorder=window.recorder;QTest.qWait(150)
        window.peer=None;window.on_advanced_event('disconnected',{})
        assert recorder.wait() and recorder.result['success']
        QTest.qWait(50);assert window.recorder is None and (tmp_path/'sessao.mp4').is_file()
    finally:window.peer=None;window.close();QTest.qWait(30)
