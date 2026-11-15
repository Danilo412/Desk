import threading,time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
from novoacesso.app import MainWindow,Prompt
from novoacesso.identity import IdentityStore
from novoacesso.numeric_invite import NumericInvite
from novoacesso.wire import make_invitation
from test_numeric_invite import Hub

def test_warm_directory_reuses_connection_and_early_notice_does_not_approve(tmp_path):
    hub=Hub();events=[];ready=[threading.Event(),threading.Event()];hosts=[]
    try:
        for i in range(2):
            store=IdentityStore(tmp_path/str(i));_,token=make_invitation('127.0.0.1',4433,store.certificate_fingerprint)
            def event(kind,data,i=i):
                events.append((i,kind))
                if kind=='numeric_ready':ready[i].set()
            hosts.append(NumericInvite(token,'synthetic-key',event,hub.client,store).start())
        assert all(r.wait(3) for r in ready)
        connections_before=hub.seq;hosts[0].detach_for_lookup()
        result=hosts[0].resolve(hosts[1].code,timeout=3,notify=True)
        assert result['token']==hosts[1].token and hub.seq==connections_before
        assert (1,'incoming_lookup') in events
        assert not any(kind=='connected' for _,kind in events)
        from metered_realtime import Presence,Direct
        assert hosts[0].client.handlers[Presence]==[]
        assert len(hosts[0].client.handlers[Direct])==1
    finally:
        for host in hosts:host.stop()
        for host in hosts:host.thread.join(3)
    assert not hub.clients

def test_chat_toast_is_plain_text_nonactivating_and_respects_preview_setting(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    try:
        window.on_event('chat',{'text':'<b>mensagem de teste</b>'})
        toast=window.notifications.toast
        assert toast and toast.isVisible() and toast.body.textFormat()==Qt.TextFormat.PlainText
        assert toast.body.text()=='<b>mensagem de teste</b>'
        assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert toast.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus
        window.identity.configure(notification_previews=False)
        window.on_event('chat',{'text':'texto privado'})
        assert 'texto privado' not in toast.body.text()
        window.identity.configure(notifications_enabled=False);toast.hide()
        window.on_event('chat',{'text':'sem aviso'})
        assert not toast.isVisible()
    finally:window.close();QApplication.processEvents()

def test_incoming_file_dialog_comes_forward_but_cancel_never_saves(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();seen=[]
    def cancel():
        dialog=QApplication.activeModalWidget()
        seen.append(bool(dialog.windowFlags()&Qt.WindowType.WindowStaysOnTopHint));dialog.reject()
    try:
        prompt=Prompt('save_file',dict(name='arquivo-de-teste.txt',size=100))
        QTimer.singleShot(40,cancel);window.on_prompt(prompt)
        assert seen==[True] and prompt.answer is None
        assert window.notifications.last_kind=='file_offer'
        assert not window.notifications.toast.isVisible()
        assert not list(tmp_path.glob('arquivo-de-teste.txt'))
    finally:window.close();QApplication.processEvents()

def test_early_lookup_notice_never_changes_permissions_or_trust(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow()
    before=window.identity.data['trusted'].copy();permissions=window.permissions()
    try:
        window.numeric_invite=SimpleNamespace(id='current',stop=lambda:None)
        window.on_event('incoming_lookup',dict(id='current',text='Preparando conexão de teste'))
        assert window.notifications.last_kind=='connection'
        assert window.identity.data['trusted']==before and window.permissions()==permissions
        assert not window.identity.settings().get('unattended') and window.peer is None
    finally:window.close();QApplication.processEvents()
