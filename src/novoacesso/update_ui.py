"""Non-modal update discovery, with local confirmation before installation."""
import os
import threading
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QTimer,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QHBoxLayout,QProgressBar
from . import __version__
from . import updater

class UpdateController(QObject):
    checked=Signal(object,str,bool)
    downloaded=Signal(object,str)
    progress=Signal(int)
    def __init__(self,window):
        super().__init__(window);self.window=window;self.available=None;self.checking=False;self.downloading=False
        self.cancel=threading.Event();self.dialog=None;self.download_path=None;self.installation=updater.installed_directory()
        self.notified_version=None
        self.checked.connect(self.on_checked);self.downloaded.connect(self.on_downloaded);self.progress.connect(self.on_progress)
        self.timer=QTimer(self);self.timer.setInterval(5*60*1000);self.timer.timeout.connect(self.check)
        if self.installation and os.environ.get('NOVOACESSO_OFFLINE')!='1':
            self.timer.start();QTimer.singleShot(15000,self.check)
    def check(self,manual=False):
        if self.window.closing or self.checking or self.downloading:return
        if os.environ.get('NOVOACESSO_OFFLINE')=='1':
            if manual:self.window.notice('A busca de atualizações está desativada neste modo de teste.')
            return
        self.checking=True
        self.window.update_check_button.setEnabled(False);self.window.update_status_label.setText('Consultando as versões publicadas…')
        if manual:self.window.statusBar().showMessage('Verificando atualizações…')
        def worker():
            result=None;error=''
            try:result=updater.check_update(__version__)
            except Exception as ex:error=str(ex)
            try:self.checked.emit(result,error,manual)
            except RuntimeError:pass
        threading.Thread(target=worker,daemon=True).start()
    def on_checked(self,update,error,manual):
        self.checking=False
        if self.window.closing:return
        self.window.update_check_button.setEnabled(True)
        self.window.update_last_check.setText('Última verificação: '+datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S'))
        if error:
            self.window.update_status_label.setText(error)
            if manual:self.window.notice(error)
            return
        self.available=update
        self.window.update_available_button.setVisible(update is not None)
        if update:self.window.update_available_button.setText('Atualizar · '+update.version)
        self.window.update_offer_button.setVisible(update is not None)
        self.window.update_status_label.setText('Desk '+update.version+' disponível para atualizar.' if update else 'Desk '+__version__+' instalado. Nenhuma versão mais nova foi encontrada no canal oficial.')
        if update and self.notified_version!=update.version:
            self.notified_version=update.version
            self.window.notifications.notify('update','Atualização do Desk disponível','Desk '+update.version+' já pode ser baixado. Abra o Desk para conferir e instalar.',destination='updates')
        if manual:
            if update:self.show_offer()
    def busy(self):
        w=self.window
        def active(peer):
            return peer is not None and not peer.closed.is_set()
        return bool(active(w.peer) or w.connecting or active(getattr(w.host,'peer',None)) or active(getattr(w.persistent,'peer',None)) or getattr(w,'recorder',None) or getattr(w,'recording_finishing',False) or w.prompts)
    def show_offer(self):
        if not self.available:self.check(True);return
        if self.dialog:self.dialog.show();self.dialog.raise_();return
        d=self.dialog=QDialog(self.window);d.setWindowTitle('Atualização do Desk');d.setMinimumWidth(460)
        d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True);layout=QVBoxLayout(d)
        title=QLabel('Desk '+self.available.version+' disponível');title.setObjectName('connectorName');layout.addWidget(title)
        notes=QLabel(self.available.notes);notes.setTextFormat(Qt.TextFormat.PlainText);notes.setWordWrap(True);layout.addWidget(notes)
        text=QLabel('Seu número, favoritos e configurações serão mantidos. Termine a sessão remota antes de instalar.');text.setWordWrap(True);layout.addWidget(text)
        if not self.installation:
            text=QLabel('Esta edição não pode atualizar a instalação diretamente. Use o instalador do Desk ou a Microsoft Store, conforme sua edição.');text.setWordWrap(True);layout.addWidget(text)
        self.bar=QProgressBar();self.bar.hide();layout.addWidget(self.bar)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
        row=QHBoxLayout();later=QPushButton('Mais tarde');later.clicked.connect(d.close);row.addWidget(later)
        self.action=QPushButton('Baixar atualização');self.action.setEnabled(bool(self.installation));self.action.clicked.connect(self.download);row.addWidget(self.action);layout.addLayout(row)
        d.destroyed.connect(self.dialog_destroyed);d.show()
    def dialog_destroyed(self,*args):
        if self.downloading:self.cancel.set()
        self.dialog=None;self.download_path=None
    def download(self):
        if self.downloading or not self.available or not self.installation:return
        if self.busy():self.message.setText('Encerre a sessão e a gravação antes de atualizar.');return
        self.downloading=True;self.cancel.clear();self.action.setEnabled(False);self.bar.setValue(0);self.bar.show()
        self.message.setText('Baixando e conferindo o instalador…')
        update=self.available;cache=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Desk/Updates'
        def worker():
            path=None;error=''
            try:path=updater.download_update(update,cache,lambda n,total:self.progress.emit(int(n*100/total)),self.cancel)
            except Exception as ex:error=str(ex)
            try:self.downloaded.emit(path,error)
            except RuntimeError:pass
        threading.Thread(target=worker,daemon=True).start()
    def on_progress(self,value):
        if self.dialog:self.bar.setValue(value)
    def on_downloaded(self,path,error):
        self.downloading=False
        if not self.dialog:return
        self.action.setEnabled(True)
        if error:self.message.setText(error);return
        self.download_path=path
        self.message.setText('Download conferido. Clique em “Instalar e fechar o Desk” para abrir o instalador. O Windows ainda verificará a assinatura do programa.')
        self.action.setText('Instalar e fechar o Desk');self.action.clicked.disconnect();self.action.clicked.connect(self.install)
    def install(self):
        if not self.download_path or not self.installation:return
        if self.busy():self.message.setText('Encerre a sessão e a gravação antes de atualizar.');return
        try:updater.launch_installer(self.download_path,self.available,self.installation)
        except OSError as ex:
            self.message.setText('O Windows bloqueou o instalador. A versão atual continua funcionando.' if getattr(ex,'winerror',None)==4551 else 'Não foi possível abrir o instalador. A versão atual foi mantida.');return
        except Exception as ex:self.message.setText(str(ex));return
        self.window.quit_application()
    def stop(self):
        self.timer.stop();self.cancel.set()
