"""Non-modal update discovery, background verified download, and local confirmation."""
import os
import threading
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QTimer,Qt
from PySide6.QtWidgets import QDialog,QFrame,QVBoxLayout,QLabel,QPushButton,QHBoxLayout,QProgressBar
from . import __version__
from . import updater

class UpdateController(QObject):
    checked=Signal(object,str,bool)
    downloaded=Signal(object,str,str)
    progress=Signal(int)
    def __init__(self,window):
        super().__init__(window);self.window=window;self.available=None;self.checking=False;self.downloading=False
        self.cancel=threading.Event();self.dialog=None;self.download_path=None;self.downloaded_version=None
        self.download_progress=0;self.background_download=False;self.dismissed_version=None
        self.state='idle';self.last_error=''
        self.installation=updater.installed_directory();self.notified_version=None;self._exit_install_launched=False
        self.checked.connect(self.on_checked);self.downloaded.connect(self._on_downloaded_signal);self.progress.connect(self.on_progress)
        self.timer=QTimer(self);self.timer.setInterval(5*60*1000);self.timer.timeout.connect(self.check)
        if self.installation and os.environ.get('NOVOACESSO_OFFLINE')!='1':
            self.timer.start();QTimer.singleShot(15000,self.check)

    def cache_directory(self):
        return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Desk/Updates'

    def auto_download_enabled(self):
        identity=getattr(self.window,'identity',None)
        return bool(identity.settings().get('auto_download_updates',True)) if identity else True

    def auto_install_on_exit_enabled(self):
        identity=getattr(self.window,'identity',None)
        return bool(identity.settings().get('auto_install_on_exit',False)) if identity else False

    def is_ready(self):
        return bool(self.available and self.download_path and self.downloaded_version==self.available.version and Path(self.download_path).is_file())

    def _set_badge(self,text,variant):
        badge=getattr(self.window,'update_badge',None)
        if badge is None:return
        badge.setText(text);badge.setProperty('variant',variant)
        badge.style().unpolish(badge);badge.style().polish(badge)

    def sync_ui(self):
        w=self.window
        if getattr(w,'closing',False):return
        update=self.available;ready=self.is_ready()
        if hasattr(w,'update_check_button'):w.update_check_button.setEnabled(not self.checking and not self.downloading)
        if hasattr(w,'update_available_button'):
            w.update_available_button.setVisible(update is not None)
            if update:
                if ready:w.update_available_button.setText('Instalar · '+update.version)
                elif self.downloading:w.update_available_button.setText(f'Baixando · {self.download_progress}%')
                else:w.update_available_button.setText('Atualizar · '+update.version)
        if hasattr(w,'update_offer_button'):
            w.update_offer_button.setVisible(update is not None)
            if update:w.update_offer_button.setText('Instalar Desk '+update.version if ready else 'Ver atualização disponível')
        if hasattr(w,'update_progress_bar'):
            w.update_progress_bar.setVisible(self.downloading or ready)
            if ready:w.update_progress_bar.setValue(100)
            elif self.downloading:w.update_progress_bar.setValue(self.download_progress)
        if hasattr(w,'update_status_label'):
            if self.checking:
                w.update_status_label.setText('Consultando as versões publicadas…');self._set_badge('Verificando','info')
            elif self.last_error:
                w.update_status_label.setText(self.last_error);self._set_badge('Atenção','warning')
            elif ready and update:
                w.update_status_label.setText(f'Desk {update.version} baixado e verificado. Pronto para instalar.');self._set_badge('Pronto para instalar','success')
            elif self.downloading and update:
                w.update_status_label.setText(f'Baixando e conferindo Desk {update.version}… {self.download_progress}%');self._set_badge('Baixando','info')
            elif update:
                w.update_status_label.setText('Desk '+update.version+' disponível para atualizar.');self._set_badge('Disponível','info')
            elif self.state=='up_to_date':
                w.update_status_label.setText('Desk '+__version__+' instalado. Nenhuma versão mais nova foi encontrada no canal oficial.');self._set_badge('Atualizado','success')
            else:
                self._set_badge('Automático','muted')
        self.sync_banner()

    def sync_banner(self):
        w=self.window
        banner=getattr(w,'update_banner',None)
        if banner is None:return
        update=self.available
        if not update or self.dismissed_version==update.version:
            banner.hide();return
        ready=self.is_ready()
        banner.setProperty('ready',ready)
        banner.style().unpolish(banner);banner.style().polish(banner)
        if ready:
            w.update_banner_title.setText(f'Desk {update.version} pronto para instalar')
            w.update_banner_detail.setText(update.notes or 'Atualização baixada e verificada. Feche sessões e gravações para aplicar.')
            w.update_banner_action.setText('Instalar agora' if self.installation else 'Ver detalhes')
            w.update_banner_action.setEnabled(True)
            w.update_banner_progress.hide()
        elif self.downloading:
            w.update_banner_title.setText(f'Baixando atualização Desk {update.version}… {self.download_progress}%')
            w.update_banner_detail.setText('Download e conferência SHA-256 em segundo plano. Você pode continuar usando o Desk.')
            w.update_banner_action.setText('Detalhes');w.update_banner_action.setEnabled(True)
            w.update_banner_progress.setValue(self.download_progress);w.update_banner_progress.show()
        else:
            w.update_banner_title.setText(f'Desk {update.version} disponível')
            w.update_banner_detail.setText(update.notes or 'Uma nova versão verificada do Desk foi publicada no canal oficial.')
            w.update_banner_action.setText('Atualizar agora' if self.installation else 'Ver detalhes')
            w.update_banner_action.setEnabled(True)
            w.update_banner_progress.hide()
        banner.show()

    def dismiss_banner(self):
        if self.available:
            self.dismissed_version=self.available.version
        self.sync_banner()

    def banner_action(self):
        if self.is_ready():
            if not self.busy() and self.installation:
                self.show_offer()
                if self.dialog and self.is_ready():
                    self.message.setText('Download conferido. Clique em “Instalar e fechar o Desk” para abrir o instalador.')
            else:
                self.show_offer()
        else:
            self.show_offer()

    def check(self,manual=False):
        if self.window.closing or self.checking:return
        if self.downloading:
            if manual:self.show_offer()
            return
        if os.environ.get('NOVOACESSO_OFFLINE')=='1':
            if manual:self.window.notice('A busca de atualizações está desativada neste modo de teste.')
            return
        self.checking=True;self.last_error='';self.state='checking';self.sync_ui()
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
        self.window.update_last_check.setText('Última verificação: '+datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S'))
        if error:
            self.last_error=error;self.state='error';self.sync_ui()
            if manual:self.window.notice(error)
            return
        self.last_error=''
        previous_version=self.available.version if self.available else None
        self.available=update
        if update is None:
            self.download_path=None;self.downloaded_version=None;self.download_progress=0;self.state='up_to_date'
            self.sync_ui();return
        if previous_version!=update.version:
            self.dismissed_version=None
        if self.downloaded_version!=update.version or not self.download_path or not Path(self.download_path).is_file():
            cached=updater.cached_update_path(update,self.cache_directory())
            if cached is not None:
                self.download_path=cached;self.downloaded_version=update.version;self.download_progress=100;self.state='ready'
                updater.cleanup_old_downloads(self.cache_directory(),keep_path=cached)
            else:
                self.download_path=None;self.downloaded_version=None;self.download_progress=0;self.state='available'
        else:
            self.state='ready'
        self.sync_ui()
        ready=self.is_ready()
        if ready and self.notified_version!=update.version:
            self.notified_version=update.version
            self.window.notifications.notify('update','Atualização do Desk pronta','Desk '+update.version+' já foi baixado e verificado. Clique para instalar.',destination='updates')
        elif not ready and self.installation and self.auto_download_enabled() and os.environ.get('NOVOACESSO_OFFLINE')!='1' and not self.downloading:
            self.download(background=True)
        elif not ready and self.notified_version!=update.version:
            self.notified_version=update.version
            self.window.notifications.notify('update','Atualização do Desk disponível','Desk '+update.version+' já pode ser baixado. Abra o Desk para conferir e instalar.',destination='updates')
        if manual:
            self.show_offer()

    def busy(self):
        w=self.window
        def active(peer):
            return peer is not None and not peer.closed.is_set()
        return bool(active(w.peer) or w.connecting or active(getattr(w.host,'peer',None)) or active(getattr(w.persistent,'peer',None)) or getattr(w,'recorder',None) or getattr(w,'recording_finishing',False) or w.prompts)

    def show_offer(self):
        if not self.available:self.check(True);return
        if self.dialog:self.dialog.show();self.dialog.raise_();return
        d=self.dialog=QDialog(self.window);d.setWindowTitle('Atualização do Desk');d.setMinimumWidth(480)
        d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        layout=QVBoxLayout(d);layout.setContentsMargins(24,22,24,22);layout.setSpacing(12)
        header=QHBoxLayout()
        title=QLabel('Desk '+self.available.version+' disponível');title.setObjectName('connectorName');header.addWidget(title,1)
        size_mb=self.available.size/(1024*1024)
        size_label=QLabel(f'{size_mb:.1f} MB');size_label.setObjectName('updateBadge');size_label.setProperty('variant','info');header.addWidget(size_label)
        layout.addLayout(header)
        notes_card=QFrame();notes_card.setObjectName('settingsCard');notes_layout=QVBoxLayout(notes_card);notes_layout.setContentsMargins(14,12,14,12)
        notes=QLabel(self.available.notes);notes.setTextFormat(Qt.TextFormat.PlainText);notes.setWordWrap(True);notes_layout.addWidget(notes)
        layout.addWidget(notes_card)
        text=QLabel('Seu número, favoritos e configurações serão mantidos. Termine a sessão remota antes de instalar.');text.setWordWrap(True);text.setObjectName('muted');layout.addWidget(text)
        if not self.installation:
            edition=QLabel('Esta edição não pode atualizar a instalação diretamente. Use o instalador do Desk ou a Microsoft Store, conforme sua edição.');edition.setWordWrap(True);edition.setObjectName('muted');layout.addWidget(edition)
        self.bar=QProgressBar();self.bar.setFixedHeight(6);layout.addWidget(self.bar)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
        row=QHBoxLayout();later=QPushButton('Mais tarde');later.clicked.connect(d.close);row.addWidget(later);row.addStretch()
        self.action=QPushButton('Baixar atualização');self.action.setObjectName('primary');self.action.setEnabled(bool(self.installation))
        self.action.clicked.connect(lambda:self.download(background=False));row.addWidget(self.action);layout.addLayout(row)
        d.destroyed.connect(self.dialog_destroyed)
        self._refresh_dialog_state()
        d.show()

    def _refresh_dialog_state(self):
        if not self.dialog:return
        if self.is_ready():
            self.bar.setValue(100);self.bar.show()
            self.action.setEnabled(bool(self.installation))
            self.action.setText('Instalar e fechar o Desk')
            try:self.action.clicked.disconnect()
            except RuntimeError:pass
            self.action.clicked.connect(self.install)
            self.message.setText('Download conferido. Clique em “Instalar e fechar o Desk” para abrir o instalador. O Windows ainda verificará a assinatura do programa.')
        elif self.downloading:
            self.bar.setValue(self.download_progress);self.bar.show()
            self.action.setEnabled(False);self.action.setText('Baixando…')
            self.message.setText('Baixando e conferindo o instalador…')
        else:
            self.bar.hide()
            self.action.setEnabled(bool(self.installation))
            self.action.setText('Baixar atualização')

    def dialog_destroyed(self,*args):
        if self.downloading and not self.background_download and not self.auto_download_enabled():
            self.cancel.set()
        self.dialog=None
        if not self.is_ready():
            self.download_path=None

    def download(self,background=False):
        if self.downloading or not self.available or not self.installation:return
        if not background and self.busy():
            if self.dialog:self.message.setText('Encerre a sessão e a gravação antes de atualizar.')
            return
        cached=updater.cached_update_path(self.available,self.cache_directory())
        if cached is not None:
            self.download_path=cached;self.downloaded_version=self.available.version;self.download_progress=100;self.state='ready'
            self.sync_ui();self._refresh_dialog_state();return
        self.downloading=True;self.background_download=bool(background);self.download_progress=0;self.state='downloading'
        self.cancel.clear();self.last_error='';self.sync_ui()
        if self.dialog:self._refresh_dialog_state()
        update=self.available;cache=self.cache_directory()
        def worker():
            path=None;error=''
            try:
                raw_path=updater.download_update(update,cache,lambda n,total:self.progress.emit(int(n*100/max(1,total))),self.cancel)
                path=updater.promote_cached_update(update,raw_path,cache)
                updater.cleanup_old_downloads(cache,keep_path=path)
            except Exception as ex:error=str(ex)
            try:self.downloaded.emit(path,error,update.version)
            except RuntimeError:pass
        threading.Thread(target=worker,daemon=True).start()

    def on_progress(self,value):
        self.download_progress=max(0,min(100,int(value)))
        if self.dialog:self.bar.setValue(self.download_progress)
        self.sync_ui()

    def _on_downloaded_signal(self,path,error,version):
        self.on_downloaded(path,error,version)

    def on_downloaded(self,path,error,version=None):
        self.downloading=False
        self.background_download=False
        if error:
            self.state='error';self.last_error=error;self.sync_ui()
            if self.dialog:
                self.action.setEnabled(bool(self.installation))
                self.message.setText(error)
            return
        target_version=version or (self.available.version if self.available else None)
        self.download_path=path;self.downloaded_version=target_version;self.download_progress=100;self.state='ready'
        self.sync_ui()
        if target_version and self.notified_version!=target_version and not self.dialog:
            self.notified_version=target_version
            self.window.notifications.notify('update','Atualização do Desk pronta','Desk '+target_version+' já foi baixado e verificado. Clique para instalar.',destination='updates')
        if self.dialog:
            self.action.setEnabled(True)
            self.download_path=path
            self.message.setText('Download conferido. Clique em “Instalar e fechar o Desk” para abrir o instalador. O Windows ainda verificará a assinatura do programa.')
            self.action.setText('Instalar e fechar o Desk')
            try:self.action.clicked.disconnect()
            except RuntimeError:pass
            self.action.clicked.connect(self.install)

    def install(self):
        if not self.download_path or not self.installation:return
        if self.busy():
            if self.dialog:self.message.setText('Encerre a sessão e a gravação antes de atualizar.')
            else:self.window.notice('Encerre a sessão e a gravação antes de atualizar.')
            return
        try:updater.launch_installer(self.download_path,self.available,self.installation)
        except OSError as ex:
            msg='O Windows bloqueou o instalador. A versão atual continua funcionando.' if getattr(ex,'winerror',None)==4551 else 'Não foi possível abrir o instalador. A versão atual foi mantida.'
            if self.dialog:self.message.setText(msg)
            else:self.window.notice(msg)
            return
        except Exception as ex:
            if self.dialog:self.message.setText(str(ex))
            else:self.window.notice(str(ex))
            return
        self._exit_install_launched=True
        self.window.quit_application()

    def maybe_install_on_exit(self):
        if self._exit_install_launched or not self.auto_install_on_exit_enabled():return False
        if not self.is_ready() or not self.installation or self.busy():return False
        try:
            updater.launch_installer(self.download_path,self.available,self.installation)
            self._exit_install_launched=True
            return True
        except Exception:
            return False

    def stop(self):
        self.timer.stop();self.cancel.set()
