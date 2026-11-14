import re,threading
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from novoacesso.app import MainWindow,Prompt
from novoacesso.collaboration_ui import TransferPanel
from novoacesso.session import HostService,join
from test_session import FakeDesktop,wait_for

def test_chat_timestamps_plain_text_and_unread_badge(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.show()
    try:
        window.on_event('chat',{'text':'<b>Mensagem de teste</b>'})
        assert re.search(r'\[\d\d:\d\d\] Outra pessoa: <b>Mensagem de teste</b>',window.chat.toPlainText())
        assert window._unread_chat==1 and '(1)' in window.session_side.tabText(0)
        window.tabs.setCurrentIndex(1);window.open_session_panel(0);QTest.qWait(20)
        assert window._unread_chat==0 and window.session_side.tabText(0)=='Conversa'
    finally:window.close();QTest.qWait(20)

def test_real_transfer_progress_integrity_and_clear_keeps_saved_file(tmp_path):
    events=[];sent=[];destination=tmp_path/'received.bin';source=tmp_path/'source.bin';content=b'desk-test-content'*15000;source.write_bytes(content)
    host=HostService(FakeDesktop(),lambda k,d:events.append((k,d)),lambda kind,data,timeout:str(destination) if kind=='save_file' else True,{})
    token=host.start('127.0.0.1');peer=None
    try:
        peer=join(token,lambda k,d:sent.append((k,d)),lambda *a:None);peer.start();peer.send_file(source)
        wait_for(lambda:any(k=='transfer' and d['state']=='verified' for k,d in events))
        wait_for(lambda:any(k=='transfer' and d['state']=='sent' for k,d in sent))
        assert destination.read_bytes()==content
        outgoing=[d for k,d in sent if k=='transfer'];incoming=[d for k,d in events if k=='transfer']
        assert {'hashing','waiting','sending','sent'}<={d['state'] for d in outgoing}
        assert incoming[-1]['state']=='verified' and incoming[-1]['done']==len(content)
        panel=TransferPanel()
        for data in outgoing+incoming:panel.update_transfer(data)
        assert len(panel.records)==2 # identical ID in opposite directions stays separate
        assert any(r['state']=='sent' for r in panel.records.values()) and any(r['state']=='verified' for r in panel.records.values())
        panel.clear_finished();assert not panel.records and destination.read_bytes()==content
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_declined_file_does_not_report_sent_or_verified(tmp_path):
    events=[];sent=[];source=tmp_path/'declined.bin';source.write_bytes(b'test')
    host=HostService(FakeDesktop(),lambda k,d:events.append((k,d)),lambda kind,data,timeout:kind=='consent',{})
    token=host.start('127.0.0.1');peer=None
    try:
        peer=join(token,lambda k,d:sent.append((k,d)),lambda *a:None);peer.start();peer.send_file(source)
        wait_for(lambda:any(k=='transfer' and d['state']=='declined' for k,d in sent))
        assert not any(k=='transfer' and d['state'] in ('sent','verified') for k,d in sent+events)
        assert not host.peer.transfers
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_failed_integrity_is_not_saved_or_shown_as_verified(tmp_path):
    events=[];destination=tmp_path/'must-not-exist.bin'
    host=HostService(FakeDesktop(),lambda k,d:events.append((k,d)),lambda kind,data,timeout:str(destination) if kind=='save_file' else True,{})
    token=host.start('127.0.0.1');peer=None;id='ab'*8
    try:
        peer=join(token,lambda *a:None,lambda *a:None);peer.start()
        peer.send(dict(type='file_offer',id=id,name='test.bin',size=4,sha256='00'*32));wait_for(lambda:id in host.peer.transfers)
        peer.channel.send(b'F',id.encode()+b'test');peer.send(dict(type='file_end',id=id))
        wait_for(lambda:any(k=='transfer' and d['state']=='failed' for k,d in events))
        wait_for(lambda:not list(tmp_path.glob('.novoacesso-*.part')))
        assert not destination.exists() and not any(k=='transfer' and d['state']=='verified' for k,d in events)
    finally:
        if peer:peer.close();peer.wait_for_workers()
        host.stop()

def test_file_destination_prompt_withdraws_without_writing(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path/'state'));window=MainWindow();cancelled=threading.Event()
    try:
        prompt=Prompt('save_file',dict(name='not-written.bin',size=123,_cancelled=cancelled.is_set))
        QTimer.singleShot(30,cancelled.set);window.on_prompt(prompt)
        assert prompt.answer is None and prompt.done.is_set() and not window.prompts and QApplication.activeModalWidget() is None
    finally:window.close();QTest.qWait(20)
