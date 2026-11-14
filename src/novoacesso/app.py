from __future__ import annotations
import argparse
from dataclasses import dataclass,field
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time

from PySide6.QtCore import Qt,QObject,Signal,QTimer,QRectF
from PySide6.QtGui import QColor,QImage,QPainter,QPen,QFont,QAction,QShortcut,QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QLineEdit,QPlainTextEdit,QCheckBox,QComboBox,QTabWidget,QFrame,
    QFileDialog,QMessageBox,QSplitter,QSizePolicy,QListWidget,QListWidgetItem,QSystemTrayIcon,QMenu,QStyle,QScrollArea,QDialog,QInputDialog)
from . import __version__

@dataclass
class Prompt:
    kind:str
    data:dict
    done:threading.Event=field(default_factory=threading.Event)
    answer:object=None
    cancelled:bool=False

    def is_cancelled(self):
        if self.cancelled:return True
        check=self.data.get('_cancelled')
        try:return bool(check and check())
        except Exception:return True

class Bridge(QObject):
    message=Signal(str,object)
    prompt=Signal(object)
    joined=Signal(object)

from PySide6.QtOpenGLWidgets import QOpenGLWidget

class AcceleratedSurface(QOpenGLWidget):
    def __init__(self,canvas):
        super().__init__(canvas);self.canvas=canvas
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    def paintGL(self):
        painter=QPainter(self);self.canvas.paint_content(painter);painter.end()

class RemoteCanvas(QWidget):
    input_event=Signal(dict)
    exit_requested=Signal()
    def escape_fullscreen(self):
        self._local_escape=True;self.exit_requested.emit()
    def __init__(self):
        super().__init__();self.image=None;self.allow_control=False;self.rect=QRectF();self.last_move=0;self.display_mode='fit';self.surface=None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setMouseTracking(True)
        self.setMinimumSize(420,280);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Tela remota. Clique para focar o teclado quando o controle estiver autorizado.")
        if os.environ.get('QT_QPA_PLATFORM')!='offscreen' and os.environ.get('NOVOACESSO_RENDERER')!='cpu':
            self.surface=AcceleratedSurface(self);self.surface.show()
            QTimer.singleShot(1000,self.check_renderer)

    def check_renderer(self):
        if self.surface and not self.surface.isValid() and self.isVisible():
            self.surface.hide();self.surface.deleteLater();self.surface=None;self.update()

    def resizeEvent(self,event):
        if self.surface:self.surface.setGeometry(self.rect_for_surface())
        super().resizeEvent(event)
    def rect_for_surface(self):return self.contentsRect()

    def update(self,*args):
        super().update(*args)
        if self.surface:self.surface.update()

    def set_frame(self,image):
        raw=image.tobytes()
        self.image=QImage(raw,image.width,image.height,image.width*3,QImage.Format.Format_RGB888).copy()
        if self.display_mode=='original':self.setMinimumSize(image.width,image.height);self.resize(image.width,image.height)
        self.update()

    def paintEvent(self,event):
        if self.surface and self.surface.isValid():return
        p=QPainter(self);self.paint_content(p)

    def paint_content(self,p):
        p.fillRect(self.contentsRect(),QColor("#151515"))
        if self.image is None:
            p.setPen(QColor("#aaaaaa"));p.setFont(QFont("Segoe UI",13))
            p.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignCenter,"A tela remota aparece aqui\nquando a conexão for aprovada.")
            return
        size=self.image.size() if self.display_mode=='original' else self.image.size().scaled(self.size(),Qt.AspectRatioMode.IgnoreAspectRatio if self.display_mode=='stretch' else Qt.AspectRatioMode.KeepAspectRatio)
        self.rect=QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(self.rect,self.image)
        if self.hasFocus() and self.allow_control:
            p.setPen(QPen(QColor("#ef443b"),2));p.drawRect(self.contentsRect().adjusted(1,1,-2,-2))

    def point(self,event):
        pos=event.position()
        if not self.image or not self.rect.contains(pos) or not self.allow_control:return None
        return dict(x=min(1,max(0,(pos.x()-self.rect.x())/self.rect.width())),y=min(1,max(0,(pos.y()-self.rect.y())/self.rect.height())))

    def mouseMoveEvent(self,event):
        point=self.point(event);now=time.monotonic()
        if point and now-self.last_move>.025:
            self.last_move=now;self.input_event.emit(dict(event="move",**point))

    def mousePressEvent(self,event):
        self.setFocus();self.mouse_button(event,True)
    def mouseReleaseEvent(self,event):self.mouse_button(event,False)
    def mouse_button(self,event,down):
        point=self.point(event)
        buttons={Qt.MouseButton.LeftButton:"left",Qt.MouseButton.RightButton:"right",Qt.MouseButton.MiddleButton:"middle"}
        if point and event.button() in buttons:self.input_event.emit(dict(event="button",button=buttons[event.button()],down=down,**point))
        elif not down and self.allow_control:self.input_event.emit(dict(event="release"))
    def wheelEvent(self,event):
        if self.allow_control and self.image:self.input_event.emit(dict(event="wheel",delta=max(-1200,min(1200,event.angleDelta().y()))))
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and self.window().isFullScreen():
            self.escape_fullscreen();event.accept();return
        if self.allow_control and not event.isAutoRepeat():
            vk=event.nativeVirtualKey()
            if 1<=vk<=254:self.input_event.emit(dict(event="key",vk=vk,down=True))
            event.accept()
        else:super().keyPressEvent(event)
    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and getattr(self,'_local_escape',False):
            self._local_escape=False;event.accept();return
        if self.allow_control and not event.isAutoRepeat():
            vk=event.nativeVirtualKey()
            if 1<=vk<=254:self.input_event.emit(dict(event="key",vk=vk,down=False))
            event.accept()
    def focusOutEvent(self,event):
        self.input_event.emit(dict(event="release"));self.update();super().focusOutEvent(event)

def button(label,handler,primary=False):
    result=QPushButton(label);result.clicked.connect(handler)
    if primary:result.setObjectName("primary")
    return result

def card(title,subtitle):
    frame=QFrame();frame.setObjectName("card");layout=QVBoxLayout(frame);layout.setSpacing(12)
    label=QLabel(title);label.setObjectName("cardTitle");layout.addWidget(label)
    desc=QLabel(subtitle);desc.setWordWrap(True);desc.setObjectName("muted");layout.addWidget(desc)
    return frame,layout

from .desk_ui import DeskShell, STYLE

class MainWindow(DeskShell,QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("Desk • suporte remoto");self.resize(1220,820)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        self.bridge=Bridge(self);self.bridge.message.connect(self.on_event);self.bridge.prompt.connect(self.on_prompt);self.bridge.joined.connect(self.on_joined)
        self.peer=None;self.host=None;self.connecting=False;self.closing=False;self.prompts=[];self.last_clipboard=""
        self.connection_epoch=0;self.pending_channel=None;self.numeric_invite=None;self.cloud_signaling_key=''
        from .identity import IdentityStore
        self.identity=IdentityStore();self.persistent=None;self.session_gate=threading.Lock();self.force_exit=False
        self.backend=None;self._fullscreen=False;self.fullscreen_window=None
        self.control_authorized=False
        self.frame_lock=threading.Lock();self.latest_frame=None;self.available_profile='';self.last_connection_profile=''
        self.active_saved_id=None;self.next_saved_id=None;self.reconnect_profile='';self.manual_disconnect=True;self.retry_count=0
        self.retry_timer=QTimer(self);self.retry_timer.setSingleShot(True);self.retry_timer.timeout.connect(self.retry_connection)
        self.build_shell()
        self.apply_view_preferences(self.identity.settings().get('view'))
        self.frame_timer=QTimer(self);self.frame_timer.setInterval(16);self.frame_timer.timeout.connect(self.render_latest_frame);self.frame_timer.start()
        self.statusBar().showMessage("Nenhum acesso remoto ativo.")
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.tray=QSystemTrayIcon(self.windowIcon(),self)
        menu=QMenu(self);open_action=menu.addAction('Abrir Desk');open_action.triggered.connect(self.showNormal)
        stop_action=menu.addAction('Desativar acesso permanente');stop_action.triggered.connect(lambda:self.unattended.setChecked(False))
        quit_action=menu.addAction('Sair');quit_action.triggered.connect(self.quit_application)
        self.tray.setContextMenu(menu);self.tray.setToolTip('Desk • acesso permanente');self.tray.activated.connect(lambda reason:self.showNormal() if reason==QSystemTrayIcon.ActivationReason.DoubleClick else None)
        settings=self.identity.settings()
        for widget,key in ((self.allow_control,'control'),(self.allow_clipboard,'clipboard'),(self.allow_audio,'audio')):
            widget.blockSignals(True);widget.setChecked(settings.get('permissions',{}).get(key,False));widget.blockSignals(False)
        if settings.get('unattended'):QTimer.singleShot(200,self.start_persistent)

    def _build_home(self):
        return self.build_home()


    def _build_session(self):
        self.build_session_page()

    def _build_saved(self):
        return self.build_saved()


    def refresh_saved(self):
        return self.refresh_saved_views()


    def store_saved(self):
        try:
            from .saved_connections import save_connection
            profile=self.saved_profile.toPlainText().strip()
            id=save_connection(self.identity,self.saved_name.text(),profile,self.saved_password.text(),view=self.view_preferences())
            if self.peer and self.peer.role=='viewer' and profile in (self.available_profile,self.last_connection_profile):
                self.active_saved_id=id;self.reconnect_profile=profile;self.last_connection_profile=profile
            self.saved_password.clear();self.saved_profile.clear();self.refresh_saved();self.activity.setText('Computador salvo. Use Conectar ou dê dois cliques no nome.')
        except Exception as ex:self.notice(str(ex))

    def connect_saved(self):
        item=self.saved_list.currentItem()
        if not item:return
        entry=item.data(Qt.ItemDataRole.UserRole);password=''
        if entry['locked']:
            password,ok=QInputDialog.getText(self,'Abrir acesso salvo','Senha local para '+entry['name'],QLineEdit.EchoMode.Password)
            if not ok:return
        try:
            from .saved_connections import open_connection,list_connections
            entry=next((item for item in list_connections(self.identity) if item['id']==entry['id']),entry)
            token=open_connection(self.identity,entry['id'],password)
            self.apply_view_preferences(entry.get('view'));self.next_saved_id=entry['id']
            self.remote_invite.setPlainText(token);self.connect_peer()
        except Exception as ex:self.notice(str(ex))

    def remove_saved(self):
        item=self.saved_list.currentItem()
        if item:
            from .saved_connections import remove_connection
            remove_connection(self.identity,item.data(Qt.ItemDataRole.UserRole)['id']);self.refresh_saved()

    def save_current_computer(self):
        if not self.peer or self.peer.role!='viewer':self.notice('Conecte primeiro ao computador que deseja salvar.');return
        self.exit_fullscreen()
        profile=self.available_profile or self.last_connection_profile
        if not profile.startswith('NAU1-'):
            lookup=getattr(self.peer,'address_lookup',None)
            if lookup:
                self.add_address_favorite(address=lookup['code']);return
            self.notice('No computador acessado, clique em Permitir reconexão deste dispositivo. A autorização é confirmada lá uma única vez.');return
        self.saved_profile.setPlainText(profile);self.tabs.setCurrentWidget(self.saved_page);self.saved_name.setFocus()

    def enable_saved_access(self):
        if not self.peer or self.peer.role!='host':self.notice('Esta opção deve ser usada no computador que está sendo acessado.');return
        public=getattr(self.peer,'device_public',None)
        if not public:self.notice('O outro computador não forneceu uma identidade de dispositivo.');return
        if not self.identity.trusted(public):self.trust_current()
        if not self.identity.trusted(public):return
        if not self.unattended.isChecked():self.unattended.setChecked(True)
        if self.persistent:self.share_permanent_profile()

    def share_permanent_profile(self):
        if self.peer and self.peer.role=='host' and self.identity.trusted(getattr(self.peer,'device_public','')) and self.permanent_profile.toPlainText():
            self.peer.send(dict(type='permanent_profile',profile=self.permanent_profile.toPlainText(),name=socket.gethostname()[:80]))

    def _build_about(self):
        return self.build_about()


    def _build_network(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(24,24,24,24)
        title=QLabel('Internet e dispositivos autorizados');title.setObjectName('headline');layout.addWidget(title)
        settings=self.identity.settings()
        cloud_key='';cloud={}
        from .wire import ProtocolError
        try:
            config_path=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])/'internet.json'
            cloud={} if os.environ.get('NOVOACESSO_OFFLINE')=='1' else json.loads(config_path.read_text(encoding='utf-8'))
            candidate=cloud.get('public_key','')
            if candidate and cloud.get('ice_servers'):
                from .relay import token_encode,validate_endpoint
                candidate=token_encode('NAR1-',validate_endpoint(dict(mode='metered',api_key=candidate,ice_servers=cloud['ice_servers'])))
            from .relay import endpoint_from_token
            if candidate and endpoint_from_token(candidate).get('mode')=='metered':cloud_key=candidate
        except (OSError,ValueError,TypeError,AttributeError,ProtocolError):pass
        if cloud_key:self.cloud_signaling_key=cloud.get('public_key','')
        self.shipped_cloud_key=cloud_key;self.shipped_cloud_revision=cloud.get('config_revision','')
        saved_config=settings.get('relay_config') or ''
        if cloud_key and saved_config and cloud.get('provider')=='ExpressTURN':
            try:
                from .network_config import use_shipped_relay
                if use_shipped_relay(saved_config,cloud,settings):
                    saved_config=cloud_key;settings['use_relay']=True
                    self.identity.configure(relay_config=cloud_key,use_relay=True,shipped_relay_revision=self.shipped_cloud_revision)
            except ProtocolError:pass
        self.build_settings_page(settings,saved_config,cloud_key)

    def relay_endpoint(self):
        if not self.use_relay.isChecked():return None
        from .relay import endpoint_from_token
        return endpoint_from_token(self.relay_config.text())
    def apply_network(self):
        try:
            self.relay_endpoint()
            value=self.relay_config.text().strip()
            self.identity.configure(relay_config=value,use_relay=self.use_relay.isChecked(),relay_customized=value!=self.shipped_cloud_key,shipped_relay_revision=self.shipped_cloud_revision)
            if self.unattended.isChecked():self.start_persistent()
            self.activity.setText('Configuração de conexão salva neste usuário.')
        except Exception as ex:self.notice(str(ex))
    def test_relay(self):
        try:
            endpoint=self.relay_endpoint()
            if not endpoint or endpoint.get('mode')!='metered' or not endpoint.get('ice_servers'):raise ValueError('Ative a configuração de internet com um servidor TURN para testar.')
            config=dict(public_key=endpoint['api_key'],ice_servers=endpoint['ice_servers'])
        except Exception as ex:self.relay_test_status.setText(str(ex));return
        self.relay_test_button.setEnabled(False);self.relay_test_status.setText('Testando usuário e senha TURN por TCP e UDP…')
        def check():
            import asyncio
            from .turn_validation import validate_config
            try:result=asyncio.run(validate_config(config))
            except Exception:result=dict(passed=False,checks=[{'message':'Não foi possível validar o relay.'}])
            self.emit_event('relay_check',result)
        threading.Thread(target=check,daemon=True).start()
    def unattended_changed(self,enabled):
        if enabled:
            result=QMessageBox.question(self,'Habilitar acesso permanente?','Dispositivos autorizados poderão acessar este computador sem nova aprovação enquanto o aplicativo estiver ativo. As permissões selecionadas serão aplicadas. O ícone ficará visível na bandeja. Habilitar?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if result!=QMessageBox.StandardButton.Yes:
                self.unattended.blockSignals(True);self.unattended.setChecked(False);self.unattended.blockSignals(False);return
            self.identity.configure(unattended=True);self.start_persistent()
        else:
            self.identity.configure(unattended=False)
            if self.persistent:self.persistent.stop();self.persistent=None
            self.permanent_profile.clear();self.tray.hide();self.status.setText('Acesso permanente desativado')
    def start_persistent(self):
        try:
            if self.persistent:self.persistent.stop();self.persistent=None
            from .desktop import DesktopBackend
            from .unattended import TrustedHost
            self.persistent=TrustedHost(DesktopBackend(),self.emit_persistent,self.request,self.permissions(),identity=self.identity,relay=self.relay_endpoint(),gate=self.session_gate)
            profile=self.persistent.start(self.address.currentText().strip())
            self.permanent_profile.setPlainText(profile);self.tray.show();self.status.setText('Conectando ao relay' if self.persistent.relay else 'Acesso permanente disponível')
            self.share_permanent_profile()
        except Exception as ex:
            if self.persistent:self.persistent.stop();self.persistent=None
            self.identity.configure(unattended=False);self.unattended.blockSignals(True);self.unattended.setChecked(False);self.unattended.blockSignals(False);self.notice('Não foi possível habilitar: '+str(ex))
    def emit_persistent(self,name,data):
        if name=='connected':data=dict(data,persistent=True)
        self.emit_event(name,data)
    def trust_current(self):
        public=getattr(self.peer,'device_public',None) if self.peer and self.peer.role=='host' else None
        if not public:self.notice('Primeiro receba e aprove uma conexão por convite do dispositivo que deseja autorizar.');return
        if QMessageBox.question(self,'Autorizar dispositivo?',f'Autorizar permanentemente o dispositivo {public[:16]}…? Você poderá revogá-lo nesta lista.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.identity.trust(public,'Dispositivo '+public[:12]);self.refresh_trusted()
    def refresh_trusted(self):
        self.trusted_devices.clear()
        for public,data in self.identity.data['trusted'].copy().items():
            item=QListWidgetItem(data['name']+' • '+public[:16]);item.setData(Qt.ItemDataRole.UserRole,public);self.trusted_devices.addItem(item)
    def revoke_current(self):
        item=self.trusted_devices.currentItem()
        if item:
            public=item.data(Qt.ItemDataRole.UserRole);self.identity.revoke(public)
            if self.persistent and self.persistent.peer and getattr(self.persistent.peer,'device_public',None)==public:self.persistent.peer.close('Dispositivo revogado localmente.')
            self.refresh_trusted()
    def autostart_changed(self,enabled):
        try:
            from .startup import set_autostart
            set_autostart(enabled);self.identity.configure(autostart=enabled)
        except Exception as ex:
            self.autostart.blockSignals(True);self.autostart.setChecked(not enabled);self.autostart.blockSignals(False);self.notice(str(ex))

    def emit_event(self,name,data):
        if self.closing:return
        if name=='frame':
            with self.frame_lock:self.latest_frame=data
        else:self.bridge.message.emit(name,data)

    def render_latest_frame(self):
        with self.frame_lock:image=self.latest_frame;self.latest_frame=None
        if image is not None and not self.closing:
            self.canvas.set_frame(image)
            if self._connection_state=='receiving':self.show_connection_state('active')

    def request(self,kind,data,timeout):
        if self.closing:return None
        prompt=Prompt(kind,data);self.bridge.prompt.emit(prompt)
        deadline=time.monotonic()+timeout
        while True:
            if self.closing or prompt.is_cancelled():prompt.cancelled=True;return None
            remaining=deadline-time.monotonic()
            if remaining<=0:prompt.cancelled=True;return None
            if prompt.done.wait(min(.05,remaining)):return None if prompt.is_cancelled() else prompt.answer

    def on_prompt(self,prompt):
        if self.closing or prompt.is_cancelled():prompt.cancelled=True;prompt.done.set();return
        self.prompts.append(prompt)
        try:
            if prompt.kind=="consent":
                prompt.answer=self.consent_dialog(prompt)
            elif prompt.kind=="save_file":
                name=prompt.data["name"];size=prompt.data["size"]
                dialog=QFileDialog(self.fullscreen_window or self,f"Receber {name} ({size/1024:.1f} KB)",str(Path.home()/"Downloads"))
                dialog.setOption(QFileDialog.Option.DontUseNativeDialog,True);dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave);dialog.setFileMode(QFileDialog.FileMode.AnyFile);dialog.selectFile(name)
                timer=QTimer(dialog);timer.setInterval(75);timer.timeout.connect(lambda:dialog.reject() if prompt.is_cancelled() or self.closing else None);timer.start()
                allowed=dialog.exec()==QFileDialog.DialogCode.Accepted and not prompt.is_cancelled() and not self.closing
                prompt.answer=dialog.selectedFiles()[0] if allowed and dialog.selectedFiles() else None;dialog.deleteLater()
        finally:
            if prompt.is_cancelled():prompt.answer=None
            prompt.done.set();self.prompts.remove(prompt)

    def permissions(self):return dict(control=self.allow_control.isChecked(),clipboard=self.allow_clipboard.isChecked(),audio=self.allow_audio.isChecked())
    def start_host(self):
        if self.peer or self.connecting:self.notice("Encerre a sessão atual antes de gerar um convite.");return
        self.stop_sharing()
        try:
            from .desktop import DesktopBackend
            from .session import HostService
            self.backend=DesktopBackend()
            self.host=HostService(self.backend,self.emit_event,self.request,self.permissions(),identity=self.identity,relay=self.relay_endpoint(),gate=self.session_gate)
            address=self.address.currentText().strip()
            if not address or any(c.isspace() for c in address):raise ValueError("Informe um endereço de rede válido.")
            token=self.host.start(address)
            self.invite.setPlainText(token);self.status.setText("Aguardando aprovação local")
            self.activity.setText("Convite criado. Compartilhe-o com a pessoa do suporte. Se o Windows perguntar sobre rede, autorize apenas a rede em que pretende usar o aplicativo.")
            self.make_invite.setEnabled(False)
            endpoint=self.relay_endpoint();key=endpoint.get('api_key') if endpoint and endpoint.get('mode')=='metered' else self.cloud_signaling_key
            if key:
                from .numeric_invite import NumericInvite
                self.numeric_code.setPlaceholderText('Preparando código…')
                self.numeric_invite=NumericInvite(token,key,self.emit_event,identity=self.identity);self.numeric_invite.start()
            else:self.numeric_code.setPlaceholderText('Use o convite completo neste modo')
        except Exception as ex:
            if self.host:self.host.stop();self.host=None
            self.notice("Não foi possível compartilhar: "+str(ex))

    def stop_sharing(self):
        if self.numeric_invite:self.numeric_invite.stop();self.numeric_invite=None
        self.show_fixed_address();self._desk_address_online=False
        self.set_availability('preparing' if self._desk_listening_requested else 'offline')
        if self.host:self.host.stop();self.host=None
        if self.peer and self.peer.role=="host":self.peer=None
        self.invite.clear();self.make_invite.setEnabled(True)
    def stop_all_sharing(self):
        self._desk_listening_requested=False;self.address_timer.stop()
        self.stop_sharing()
        if self.unattended.isChecked():self.unattended.setChecked(False)
        self.status.setText('Recebimento pausado');self.address_caption.setText('Seu endereço fixo foi mantido · recebimento pausado')

    def _legacy_copy_invite(self):
        value=self.numeric_code.text() or self.invite.toPlainText()
        if value:QApplication.clipboard().setText(value);self.activity.setText('Código copiado.' if self.numeric_code.text() else 'Convite completo copiado.')

    def connect_peer(self,retry=False):
        if not self.remote_invite.toPlainText().strip():
            self.remote_invite.setFocus();self.activity.setText("Digite ou cole o endereço do outro dispositivo.");return
        self._desk_last_remote=self.remote_invite.toPlainText().strip();self.address_timer.stop()
        if self.peer or self.connecting:self.notice("Já existe uma conexão ativa ou em andamento.");return
        if self.persistent:self.notice('Desative o acesso permanente deste computador antes de acessar outro computador nesta janela.');return
        self.stop_sharing();token=self.remote_invite.toPlainText().strip()
        if not token:self.notice("Digite o código ou cole o convite do outro computador.");return
        self.retry_timer.stop()
        if not retry:
            self.manual_disconnect=False;self.retry_count=0
            self.active_saved_id=self.next_saved_id;self.next_saved_id=None
            self.reconnect_profile=token if token.startswith('NAU1-') else ''
        endpoint=self.relay_endpoint();numeric_key=endpoint.get('api_key') if endpoint and endpoint.get('mode')=='metered' else self.cloud_signaling_key
        self.connecting=True;self.connect_button.setEnabled(False);self.status.setText("Aguardando o outro computador")
        self.connection_epoch+=1;epoch=self.connection_epoch
        with self.frame_lock:self.latest_frame=None
        self.canvas.image=None;self.canvas.allow_control=False;self.canvas.update()
        self.show_connection_state('connecting');self.tabs.setCurrentIndex(1)
        def current_event(name,data):
            if self.closing or epoch!=self.connection_epoch:return
            if name=='frame':
                with self.frame_lock:
                    if epoch==self.connection_epoch:self.latest_frame=data
            else:self.emit_event(name,dict(data,_ui_epoch=epoch))
        def remember(channel):
            if self.closing or epoch!=self.connection_epoch:
                channel.close();raise ConnectionError("Conexão cancelada.")
            self.pending_channel=channel
            self.emit_event('connect_stage',{'text':'Confirmando a autorização deste dispositivo.' if token.startswith('NAU1-') else 'Aguardando autorização do outro computador. A solicitação precisa ser aceita lá.','stage':'authenticating' if token.startswith('NAU1-') else 'approval','epoch':epoch})
        def connect():
            try:
                from .session import join
                resolved=token;lookup=None
                if not token.startswith(('NA1-','NAU1-')):
                    self.emit_event('connect_stage',{'text':'Localizando o endereço na rede Desk…','stage':'locating','epoch':epoch})
                    if not numeric_key:raise ValueError('Configure o serviço de internet para usar códigos numéricos.')
                    from .numeric_invite import resolve_address
                    lookup=resolve_address(token,numeric_key,cancelled=lambda:self.closing or epoch!=self.connection_epoch,expected_public=self.identity.address_peer(token))
                    resolved=lookup['token']
                self.emit_event('connect_stage',{'text':'Estabelecendo a conexão segura com o computador remoto.','stage':'connecting','epoch':epoch})
                from .network_config import refresh_profile
                resolved=refresh_profile(resolved,endpoint)
                peer=join(resolved,current_event,self.request,on_channel=remember,identity=self.identity)
                peer.connection_profile=resolved if resolved.startswith('NAU1-') else ''
                peer.address_lookup=lookup
                peer.ui_epoch=epoch
                self.bridge.joined.emit(peer)
            except Exception as ex:
                from .wire import ProtocolError
                if epoch==self.connection_epoch:self.emit_event("connect_error",{"text":str(ex)[:250],'epoch':epoch,'retryable':not isinstance(ex,(ProtocolError,ValueError))})
        threading.Thread(target=connect,daemon=True).start()

    def on_joined(self,peer):
        if self.closing or getattr(peer,"ui_epoch",None)!=self.connection_epoch:
            peer.event=lambda *args:None;peer.close();return
        lookup=getattr(peer,'address_lookup',None)
        if lookup:
            try:self.identity.pin_address(lookup['code'],lookup['public'])
            except Exception:
                peer.close();self.pending_channel=None
                self.emit_event('connect_error',dict(text='A identidade deste endereço mudou. A conexão foi interrompida.',retryable=False));return
        self.pending_channel=None;self.connecting=False;self.connect_button.setEnabled(True)
        self.available_profile='';self.last_connection_profile=getattr(peer,'connection_profile','')
        if self.last_connection_profile:self.reconnect_profile=self.last_connection_profile
        self.retry_count=0;self.retry_timer.stop()
        self.peer=peer
        try:peer.start()
        except Exception as ex:
            self.peer=None;peer.close()
            self.emit_event('connect_error',dict(text='A conexão foi encerrada antes de iniciar a sessão: '+str(ex)[:180],epoch=self.connection_epoch,retryable=True))

    def update_permissions(self):
        self.identity.configure(permissions=self.permissions())
        if self.persistent:self.persistent.permissions=self.permissions()
        if self.persistent and self.persistent.peer:self.persistent.peer.set_permissions(self.permissions())
        if self.host:
            self.host.permissions=self.permissions()
            if self.host.peer:self.host.peer.set_permissions(self.permissions())
    def pause_changed(self):
        peer=self.peer if self.peer and self.peer.role=='host' else None
        if peer:
            with peer.options_lock:peer.paused=self.pause.isChecked()
            peer.send(dict(type="chat",text="A transmissão foi pausada pelo anfitrião." if self.pause.isChecked() else "A transmissão foi retomada."))
    def change_view(self):
        view=self.view_preferences();self.identity.configure(view=view)
        self.sync_image_panels()
        if self.active_saved_id:
            from .saved_connections import update_preferences
            update_preferences(self.identity,self.active_saved_id,view)
        if not self.auto_reconnect.isChecked():self.retry_timer.stop()
        if self.peer and self.peer.role=="viewer" and self.monitor.currentIndex()>=0:
            width,fps=self.quality.currentData()
            self.peer.send(dict(type="view",monitor=self.monitor.currentData(),mode=self.codec.currentData(),width=width,fps=fps))

    def view_preferences(self):
        width,fps=self.quality.currentData() or (1920,30)
        result=dict(width=width,fps=fps,codec=self.codec.currentData(),auto_reconnect=self.auto_reconnect.isChecked(),display=self.display.currentData())
        if self.start_fullscreen.isChecked():result['start_fullscreen']=True
        return result

    def change_display(self):
        mode=self.display.currentData();self.canvas.display_mode=mode
        self.viewer.setWidgetResizable(mode!='original')
        if mode=='original' and self.canvas.image:
            size=self.canvas.image.size();self.canvas.setMinimumSize(size);self.canvas.resize(size)
        else:self.canvas.setMinimumSize(420,280)
        self.canvas.update();self.change_view()

    def apply_view_preferences(self,value):
        from .quality import preferences
        view=preferences(value)
        for widget in (self.quality,self.codec,self.auto_reconnect):widget.blockSignals(True)
        index=next((i for i in range(self.quality.count()) if tuple(self.quality.itemData(i))==(view['width'],view['fps'])),0)
        self.quality.setCurrentIndex(index)
        self.codec.setCurrentIndex(max(0,self.codec.findData(view['codec'])));self.auto_reconnect.setChecked(view['auto_reconnect'])
        self.display.blockSignals(True);self.display.setCurrentIndex(max(0,self.display.findData(view['display'])));self.display.blockSignals(False)
        self.canvas.display_mode=view['display'];self.viewer.setWidgetResizable(view['display']!='original')
        for widget in (self.quality,self.codec,self.auto_reconnect):widget.blockSignals(False)
        self.start_fullscreen.blockSignals(True);self.start_fullscreen.setChecked(view.get('start_fullscreen',False));self.start_fullscreen.blockSignals(False)
        self.sync_image_panels()

    def schedule_reconnect(self):
        if self.closing or self.manual_disconnect or not self.reconnect_profile or not self.auto_reconnect.isChecked():return
        delay=min(30,2**min(self.retry_count,5));self.retry_count+=1;self.retry_timer.start(delay*1000)
        self.status.setText('Reconectando automaticamente…')
        self.activity.setText(f'Conexão interrompida. Nova tentativa em {delay} segundo(s). Use Desconectar para parar.')

    def retry_connection(self):
        if self.closing or self.manual_disconnect or self.peer or self.connecting or not self.auto_reconnect.isChecked():return
        self.remote_invite.setPlainText(self.reconnect_profile);self.connect_peer(retry=True)
    def control_changed(self):
        self.canvas.allow_control=bool(self.peer and self.peer.role=="viewer" and self.peer.permissions.get("control") and self.control.isChecked())
        if self.peer and self.peer.role=='viewer':
            self.control_hint.setText('Controle ativo. Clique na imagem remota para usar mouse e teclado.' if self.canvas.allow_control else 'Somente visualização. Marque Mouse e teclado.' if self.peer.permissions.get('control') else 'O computador remoto ainda precisa autorizar mouse e teclado em Nova conexão.')
        elif self.peer:self.control_hint.setText('Você está compartilhando. As permissões podem ser retiradas em Nova conexão.')
        if not self.canvas.allow_control:self.send_input(dict(event="release"))
        self.canvas.update()
    def send_input(self,data):
        if self.peer and self.peer.role=="viewer" and self.peer.permissions.get("control"):
            if self.control.isChecked() or data.get("event")=="release":self.peer.send(dict(type="input",**data))
    def send_chat(self):
        if not self.peer:self.notice("Conecte os computadores para enviar mensagens.");return
        text=self.message.text().strip()
        if text:self.peer.send(dict(type="chat",text=text));self.chat.appendPlainText("Você: "+text);self.message.clear()
    def send_file(self):
        if not self.peer:self.notice("Conecte os computadores para enviar arquivos.");return
        path,_=QFileDialog.getOpenFileName(self.fullscreen_window or self,"Escolher arquivo para enviar")
        if path:self.peer.send_file(Path(path))
    def send_clipboard(self,quiet=False):
        if not self.peer or not self.peer.permissions.get("clipboard"):
            if not quiet:self.notice("A pessoa que compartilha precisa permitir a troca de texto copiado.")
            return
        text=QApplication.clipboard().text()
        if len(text.encode())>32000:
            if not quiet:self.notice("O limite de texto copiado é 32 KB.")
            return
        self.last_clipboard=text;self.peer.send(dict(type="clipboard",text=text))
        if not quiet:self.activity.setText("Texto copiado enviado.")
    def clipboard_changed(self):
        text=QApplication.clipboard().text()
        if text.startswith(("NA1-","NAU1-","NAR1-","pk_live_")):return
        if self.sync_clipboard.isChecked() and text!=self.last_clipboard:self.send_clipboard(quiet=True)
    def apply_permissions(self):
        if not self.peer:return
        values=self.peer.permissions
        authorized=self.peer.role=='viewer' and bool(values.get('control',False))
        self.control.setEnabled(authorized)
        if authorized and not self.control_authorized:self.control.setChecked(True)
        if not authorized:self.control.setChecked(False)
        self.control_authorized=authorized
        self.control_changed()
        self.permissions_label.setText("Permissões • "+" · ".join(label+": "+("sim" if values.get(key) else "não") for key,label in [("control","controle"),("clipboard","texto"),("audio","áudio")]))
    def _core_event(self,name,data):
        if self.closing:return
        if name=='relay_check':
            self.relay_test_button.setEnabled(True)
            if data['passed']:
                modes=', '.join(r['transport'].upper() for r in data['checks'] if r['passed'])
                self.relay_test_status.setText('Relay autenticado: '+modes+'. O teste de sessão verifica a transmissão completa.')
            else:self.relay_test_status.setText(' '.join(dict.fromkeys(r.get('message','') for r in data['checks'])))
            return
        if name=='connect_stage':
            if data.get('epoch')==self.connection_epoch:self.activity.setText(data['text'])
            return
        if name.startswith('numeric_'):
            if not self.numeric_invite or data.get('id')!=self.numeric_invite.id:return
            if name=='numeric_ready':
                self.show_fixed_address();self.activity.setText('Compartilhe seu endereço fixo. A conexão exige sua aprovação.')
            else:
                self.show_fixed_address()
                if data.get('text'):self.activity.setText(data['text'])
        elif name=="frame":self.canvas.set_frame(data)
        elif name=='permanent_profile':
            self.available_profile=data['profile'];self.saved_profile.setPlainText(data['profile']);self.saved_name.setText(data['name'])
            self.activity.setText('O computador autorizou a reconexão. Clique em Salvar este computador para escolher nome e senha local.')
        elif name in ('relay_wait','relay_ready'):
            self.status.setText('Preparando conexão' if name=='relay_wait' else 'Serviço pronto • aguardando sessão');self.activity.setText(data['text'])
        elif name=="connected":
            if self.numeric_invite:self.numeric_invite.stop();self.numeric_invite=None
            self.show_fixed_address()
            if data.get('persistent') and self.persistent:self.peer=self.persistent.peer
            elif data["role"]=="host" and self.host:self.peer=self.host.peer
            if not self.peer:return
            if data.get('persistent'):
                self.tray.setToolTip('Desk • dispositivo autorizado conectado')
                self.tray.showMessage('Desk','Um dispositivo autorizado conectou-se.',QSystemTrayIcon.MessageIcon.Information,5000)
            self.status.setText("Conectado • "+("compartilhando" if self.peer.role=="host" else "acessando"));self.activity.setText("Sessão aprovada. Use Parar compartilhamento ou Desconectar para encerrar.")
            self.monitor.blockSignals(True);self.monitor.clear()
            for i,monitor in enumerate(data["monitors"]):self.monitor.addItem("Todos os monitores" if i==0 else f"Monitor {i}",i)
            if self.monitor.count()>1:self.monitor.setCurrentIndex(1)
            self.monitor.blockSignals(False);self.apply_permissions();self.tabs.setCurrentIndex(1)
            if self.canvas.allow_control:self.canvas.setFocus()
            if self.peer.role=="viewer":self.change_view()
            if self.peer.role=="host":self.pause_changed()
            self.chat.appendPlainText("Sessão aprovada. Arquivos exigem escolha local do destino.")
        elif name=="permissions":self.apply_permissions()
        elif name=="clipboard":
            if self.peer and self.peer.permissions.get("clipboard"):
                self.last_clipboard=data["text"];QApplication.clipboard().setText(data["text"])
        elif name=="chat":self.chat.appendPlainText("Outra pessoa: "+data["text"])
        elif name=="stats":
            elapsed=max(.001,data["seconds"]);text=f"{data['width']}×{data['height']} • DEFLATE {data['deflate']} / VP8 {data['vp8']} blocos no último quadro • {data['frames']/elapsed:.1f} quadros/s • {data['bytes']/elapsed/1024:.0f} KB/s médios"
            if 'effective_fps' in data:
                renderer='GPU' if self.canvas.surface and self.canvas.surface.isValid() else 'CPU'
                text+=f" • {data.get('capture','MSS')} / {renderer} • alvo {data['effective_fps']} FPS • ida e volta {data.get('rtt_ms',0):.0f} ms"
                text+=' • '+str(data.get('route',''))[:60]
            self.metrics.setText(text)
        elif name in ("notice","host_expired"):
            self.activity.setText(data["text"]);self.chat.appendPlainText("Sistema: "+data["text"])
            if name=="host_expired":
                self.make_invite.setEnabled(True);self.invite.clear();self.show_fixed_address()
                if self.numeric_invite:self.numeric_invite.stop();self.numeric_invite=None
        elif name=="connect_error":
            self.pending_channel=None;self.connecting=False;self.connect_button.setEnabled(True);self.status.setText("Não foi possível conectar")
            if data.get('retryable',False) and self.reconnect_profile and self.auto_reconnect.isChecked() and not self.manual_disconnect:
                self.activity.setText(data['text']);self.schedule_reconnect()
            else:
                self.retry_timer.stop();self.manual_disconnect=True;self.activity.setText(data['text'])
        elif name=="disconnected":
            self.exit_fullscreen()
            with self.frame_lock:self.latest_frame=None
            self.tray.setToolTip('Desk • acesso permanente' if self.persistent else 'Desk')
            self.peer=None;self.canvas.allow_control=False;self.control.setChecked(False);self.control_authorized=False
            self.status.setText('Acesso permanente disponível' if self.persistent else 'Desconectado');self.chat.appendPlainText("Sistema: "+data["text"]);self.activity.setText(data["text"])
            self.make_invite.setEnabled(True);self.permissions_label.setText("Sem sessão ativa")
            self.schedule_reconnect()
        self.statusBar().showMessage(self.status.text())
    def notice(self,text):self.activity.setText(text);QMessageBox.information(self,"Desk",text)
    def disconnect(self):
        self.manual_disconnect=True;self.retry_timer.stop();self.reconnect_profile='';self.active_saved_id=None;self.next_saved_id=None
        self.exit_fullscreen()
        with self.frame_lock:self.latest_frame=None
        self.connection_epoch+=1;self.connecting=False;self.connect_button.setEnabled(True)
        if self.pending_channel:self.pending_channel.close();self.pending_channel=None
        if self.peer:
            peer=self.peer
            peer.send(dict(type="bye"));peer.close();peer.wait_for_workers()
        self.peer=None;self.canvas.image=None;self.canvas.allow_control=False;self.canvas.update()
        self.transfer_panel.interrupt_pending()
        self.stop_sharing();self.control.setChecked(False);self.control_authorized=False;self.status.setText('Acesso permanente disponível' if self.persistent else 'Desconectado')
        if not self.closing:
            self.show_connection_state('cancelled' if self._connection_state in ('connecting','locating','approval','authenticating','reconnecting') else 'ended')
            self.session_nav.setText('Sessão')
            if self._desk_listening_requested:QTimer.singleShot(300,self.prepare_address)
    def fullscreen(self):
        if self._fullscreen:self.exit_fullscreen();return
        self._fullscreen=True;self._split_sizes=self.session_split.sizes()
        dialog=QDialog(self,Qt.WindowType.Window);dialog.setWindowTitle('Tela remota — Esc para voltar')
        layout=QVBoxLayout(dialog);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);layout.addWidget(self.viewer)
        self.fullscreen_window=dialog;dialog.rejected.connect(self.exit_fullscreen)
        self.fullscreen_escape=QShortcut(QKeySequence('Escape'),dialog);self.fullscreen_escape.activated.connect(self.canvas.escape_fullscreen)
        dialog.showFullScreen();self.canvas.setFocus();self.fullscreen_tools.reveal()

    def exit_fullscreen(self):
        if not self._fullscreen:return
        self._fullscreen=False;dialog=self.fullscreen_window;self.fullscreen_window=None
        self.fullscreen_tools.timeout.stop();self.fullscreen_tools.hide()
        self.session_split.insertWidget(0,self.viewer);self.session_split.setSizes(self._split_sizes)
        if dialog:dialog.hide();dialog.deleteLater()
        self.tabs.setCurrentIndex(1);self.canvas.setFocus()
    def closeEvent(self,event):
        if not self.persistent or self.force_exit:self.address_timer.stop()
        if self.persistent and not self.force_exit:
            self.hide();self.tray.show();event.ignore();return
        self.closing=True
        for prompt in self.prompts:prompt.cancelled=True;prompt.answer=None;prompt.done.set()
        self.disconnect()
        if self.persistent:self.persistent.stop();self.persistent=None
        self.tray.hide();event.accept()
    def quit_application(self):
        self.force_exit=True;self.close();QApplication.quit()



def main():
    parser=argparse.ArgumentParser();parser.add_argument("--smoke-test",action="store_true");parser.add_argument("--screenshot");parser.add_argument("--version",action="store_true")
    parser.add_argument("--self-test",action="store_true");parser.add_argument("--result")
    parser.add_argument('--background',action='store_true')
    parser.add_argument('--internet-test',action='store_true')
    parser.add_argument('--relay-test',action='store_true')
    parser.add_argument('--numeric-test',action='store_true')
    parser.add_argument('--hardware-test',action='store_true')
    parser.add_argument('--fixed-address-test',action='store_true')
    args=parser.parse_args()
    if args.version:print(__version__);return 0
    if args.fixed_address_test:
        from .fixed_address_diagnostics import fixed_address_test
        config=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])/'internet.json'
        cloud=json.loads(config.read_text(encoding='utf-8'))
        result=fixed_address_test(cloud['public_key'],cloud.get('ice_servers'))
        if args.result:Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result['passed'] else 1
    if args.numeric_test:
        from .diagnostics import numeric_test
        config=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])/'internet.json'
        result=numeric_test(json.loads(config.read_text(encoding='utf-8'))['public_key'])
        if args.result:Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result['passed'] else 1
    if args.internet_test or args.relay_test:
        from .diagnostics import internet_test
        config=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])/'internet.json'
        cloud=json.loads(config.read_text(encoding='utf-8'))
        result=internet_test(cloud['public_key'],cloud.get('ice_servers'),force_relay=args.relay_test)
        if args.result:Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result['passed'] else 1
    if args.self_test:
        from .diagnostics import self_test
        result=self_test()
        if args.result:Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        return 0 if result["passed"] else 1
    if os.name=="nt":
        import ctypes
        try:ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:pass
        # comtypes registra CoUninitialize no encerramento do processo.
        # A primeira importação deve pertencer à thread principal, antes do
        # Qt, e não à thread de captura, para preservar a referência COM do Qt.
        import comtypes
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(sys.argv[:1]);app.setApplicationName("Desk");app.setOrganizationName("Desk");app.setStyleSheet(STYLE)
    window=MainWindow()
    if args.background and window.identity.settings().get('unattended'):window.hide()
    else:window.show()
    QTimer.singleShot(0,window.style_native_titlebar)
    if args.hardware_test:
        # Somente dimensões/backend; nenhum pixel do desktop é gravado.
        from PIL import Image
        window.canvas.set_frame(Image.new('RGB',(1920,1080),'navy'));window.tabs.setCurrentIndex(1)
        result={};finished=threading.Event()
        def capture_probe():
            try:
                from .capture import CaptureSource
                with CaptureSource() as source:
                    image=source.image(1)
                    result['capture']=dict(backend=source.backend,dimensions=list(image.size),fallback=source.dxgi_failed)
            except Exception as ex:result['capture_error']=type(ex).__name__
            finally:finished.set()
        threading.Thread(target=capture_probe,daemon=True).start()
        def hardware_finish():
            if not finished.is_set():QTimer.singleShot(100,hardware_finish);return
            result['renderer_valid']=bool(window.canvas.surface and window.canvas.surface.isValid())
            if result['renderer_valid'] and os.name=='nt':
                import ctypes
                window.canvas.surface.makeCurrent()
                try:
                    query=ctypes.windll.opengl32.glGetString;query.argtypes=[ctypes.c_uint];query.restype=ctypes.c_char_p
                    result['renderer']=(query(0x1F01) or b'unknown').decode(errors='replace')
                finally:window.canvas.surface.doneCurrent()
            result['passed']='capture' in result
            if args.result:Path(args.result).write_text(json.dumps(result,indent=2),encoding='utf-8')
            window.close();app.quit()
        QTimer.singleShot(1500,hardware_finish)
    if args.smoke_test:
        def finish():
            if args.screenshot:window.grab().save(args.screenshot)
            window.close();app.quit()
        QTimer.singleShot(700,finish)
    return app.exec()

if __name__=="__main__":raise SystemExit(main())
