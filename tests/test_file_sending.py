import threading,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QMimeData,QUrl,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from novoacesso.app import MainWindow
from novoacesso.collaboration_ui import local_file_paths
from novoacesso.session import HostService,join,Peer
from novoacesso.folders import extract_folder
from test_session import FakeDesktop,wait_for

def test_drop_accepts_only_local_urls_and_bounded_selection(tmp_path):
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(tmp_path/'um.txt')),QUrl.fromLocalFile(str(tmp_path/'um.txt'))])
    assert [Path(path) for path in local_file_paths(mime)]==[tmp_path/'um.txt']
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path/'um.txt')),QUrl('https://example.invalid/file')]);assert not local_file_paths(mime)
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path/str(i))) for i in range(33)]);assert not local_file_paths(mime)

def test_gui_files_button_batch_and_folder_are_received_and_verified(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'viewer-state'))
    target=tmp_path/'recebidos';target.mkdir();events=[]
    first=tmp_path/'primeiro.txt';second=tmp_path/'segundo.bin';folder=tmp_path/'pasta';folder.mkdir()
    first.write_text('Desk - teste de envio',encoding='utf-8');second.write_bytes(bytes(range(256))*512);(folder/'documento.txt').write_text('Arquivo na pasta',encoding='utf-8')
    host=HostService(FakeDesktop(),lambda k,d:events.append((k,d)),lambda kind,data,timeout:str(target/data['name']) if kind=='save_file' else kind=='consent',{})
    window=MainWindow();viewer=None
    def wait_gui(predicate):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if predicate():return
            QTest.qWait(15)
        assert predicate()
    try:
        assert len([b for b in window.session_side.widget(1).findChildren(QPushButton) if b.text()=='Enviar pasta…'])==1
        assert not window.files_toolbar_button.isEnabled()
        token=host.start('127.0.0.1',bind_address='127.0.0.1')
        viewer=join(token,window.emit_event,lambda *a:None,identity=window.identity);window.peer=viewer;viewer.start()
        wait_gui(lambda:window.canvas.image is not None)
        assert window.files_toolbar_button.isEnabled() and not window.canvas.allow_control
        QTest.mouseClick(window.files_toolbar_button,Qt.MouseButton.LeftButton);assert window.session_side.currentIndex()==1
        window.send_paths([first,second,folder])
        wait_gui(lambda:len([d for k,d in events if k=='transfer' and d['state']=='verified'])==3)
        assert (target/first.name).read_bytes()==first.read_bytes() and (target/second.name).read_bytes()==second.read_bytes()
        (tmp_path/'extrair').mkdir();extracted=extract_folder(target/'pasta.zip',tmp_path/'extrair')
        assert (extracted/'documento.txt').read_bytes()==(folder/'documento.txt').read_bytes()
        assert not host.peer.permissions.get('control')
        wait_gui(lambda:len(window.transfer_panel.records)==3 and all(d['state']=='sent' for d in window.transfer_panel.records.values()))
    finally:
        window.disconnect();window.close();host.stop();QTest.qWait(30)

def test_queue_continues_after_receiver_declines_one_file(tmp_path):
    rejected=tmp_path/'recusado.txt';approved=tmp_path/'aceito.txt';rejected.write_text('não enviar');approved.write_text('enviar')
    events=[];dest=tmp_path/'destino.txt'
    def request(kind,data,timeout):
        if kind=='consent':return True
        if kind=='save_file':return str(dest) if data['name']==approved.name else None
    host=HostService(FakeDesktop(),lambda k,d:events.append((k,d)),request,{})
    token=host.start('127.0.0.1',bind_address='127.0.0.1');viewer=None;sent=[]
    try:
        viewer=join(token,lambda k,d:sent.append((k,d)),lambda *a:None);viewer.start();viewer.queue_files([rejected,approved])
        wait_for(lambda:any(k=='transfer' and d['state']=='verified' for k,d in events),10)
        assert dest.read_bytes()==approved.read_bytes()
        assert any(k=='transfer' and d['name']==rejected.name and d['state']=='declined' for k,d in sent)
        assert not any(k=='transfer' and d['name']==rejected.name and d['state']=='sent' for k,d in sent)
    finally:
        if viewer:viewer.close();viewer.wait_for_workers()
        host.stop()

def test_batch_limit_does_not_partially_enqueue():
    peer=Peer(SimpleNamespace(), 'viewer',lambda *a:None,lambda *a:None,{})
    with pytest.raises(ValueError,match='32'):peer.queue_files([Path(str(i)) for i in range(33)])
    assert peer.file_send_queue.empty() and not peer.file_sender_running
