"""Connection presentation driven by actual session events, not simulated progress."""
from __future__ import annotations
import time
from .wire import ProtocolError
from PySide6.QtCore import Qt,QEvent,QTimer
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,QProgressBar,QToolButton


class ConnectionOverlay(QWidget):
    def __init__(self,owner):
        super().__init__(owner.viewer.viewport());self.owner=owner
        self.setObjectName('connectionOverlay');self.setAutoFillBackground(True)
        outer=QVBoxLayout(self);outer.setContentsMargins(30,24,30,24);outer.addStretch()
        row=QHBoxLayout();row.addStretch();card=QFrame();card.setObjectName('connectionCard');card.setMaximumWidth(520)
        col=QVBoxLayout(card);col.setContentsMargins(30,28,30,26);col.setSpacing(16)
        self.device=QLabel('Computador remoto');self.device.setTextFormat(Qt.TextFormat.PlainText);self.device.setWordWrap(True);self.device.setObjectName('connectionDevice');col.addWidget(self.device)
        self.title=QLabel('Sua próxima conexão');self.title.setWordWrap(True);self.title.setObjectName('connectionHeading');col.addWidget(self.title)
        self.detail=QLabel();self.detail.setTextFormat(Qt.TextFormat.PlainText);self.detail.setWordWrap(True);self.detail.setObjectName('muted');col.addWidget(self.detail)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(4);col.addWidget(self.progress)
        actions=QHBoxLayout();self.primary=QPushButton();self.primary.setObjectName('primary');self.primary.clicked.connect(owner.connection_primary_action)
        self.back=QPushButton('Nova conexão');self.back.clicked.connect(owner.connection_go_home);actions.addWidget(self.primary);actions.addWidget(self.back);actions.addStretch();col.addLayout(actions)
        row.addWidget(card,1);row.addStretch();outer.addLayout(row);outer.addStretch()
        self.parent().installEventFilter(self);self.setGeometry(self.parent().rect())

    def eventFilter(self,obj,event):
        if obj is self.parent() and event.type()==QEvent.Type.Resize:self.setGeometry(obj.rect())
        return False


class FullscreenBar(QFrame):
    def __init__(self,owner):
        super().__init__(owner.viewer.viewport());self.owner=owner;self.setObjectName('fullscreenBar')
        row=QHBoxLayout(self);row.setContentsMargins(12,6,12,6);row.setSpacing(10)
        label=QLabel('Desk');label.setObjectName('brand');row.addWidget(label)
        self.monitors=QToolButton();self.monitors.setText('Monitores');self.monitors.setObjectName('sessionTool');self.monitors.setAccessibleName('Monitores em tela cheia')
        self.monitors.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.monitors.setMenu(owner.make_monitor_menu(self.monitors));row.addWidget(self.monitors)
        self.image=QToolButton();self.image.setText('Imagem');self.image.setObjectName('sessionTool');self.image.setAccessibleName('Imagem em tela cheia')
        self.image.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.image.setMenu(owner.image_menu_button.menu());row.addWidget(self.image)
        self.details=QPushButton('Info');self.details.setToolTip('Informações da sessão');self.details.clicked.connect(owner.show_session_information);row.addWidget(self.details)
        self.actions=QToolButton();self.actions.setText('Ações');self.actions.setObjectName('sessionTool');self.actions.setAccessibleName('Ferramentas em tela cheia')
        self.actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.actions.setMenu(owner.session_tools_button.menu());row.addWidget(self.actions)
        self.pin=QPushButton('Fixar');self.pin.setCheckable(True);self.pin.setChecked(owner.identity.settings().get('desk_fullscreen_bar_pinned',False))
        self.pin.setToolTip('Manter a barra visível em tela cheia');self.pin.toggled.connect(self.pin_changed);row.addWidget(self.pin)
        back=QPushButton('Voltar · Esc');back.clicked.connect(owner.exit_fullscreen);row.addWidget(back)
        self.minimize=QPushButton('Minimizar');self.minimize.setToolTip('Voltar à janela e minimizar sem encerrar a sessão');self.minimize.clicked.connect(owner.minimize_remote_session);row.addWidget(self.minimize)
        end=QPushButton('Desconectar');end.setObjectName('dangerOutline');end.clicked.connect(owner.disconnect);row.addWidget(end)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.hide_if_unused)
        owner.viewer.viewport().installEventFilter(self);owner.canvas.installEventFilter(self);self.hide()

    def reveal(self):
        if not self.owner._fullscreen:return
        self.adjustSize();self.move(max(0,(self.parent().width()-self.width())//2),0);self.show();self.raise_()
        if self.pin.isChecked():self.timeout.stop()
        else:self.timeout.start(1800)

    def pin_changed(self,pinned):
        self.owner.identity.configure(desk_fullscreen_bar_pinned=pinned);self.reveal()
        self.owner.sync_image_panels()

    def hide_if_unused(self):
        if self.pin.isChecked():return
        if self.underMouse() or any(menu.isVisible() for menu in (self.image.menu(),self.monitors.menu(),self.actions.menu())):self.timeout.start(800)
        else:self.hide()

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Resize and obj is self.parent() and self.isVisible():self.reveal()
        elif event.type()==QEvent.Type.MouseMove and self.owner._fullscreen:
            point=obj.mapTo(self.parent(),event.position().toPoint())
            if point.y()<28:self.reveal()
        return False


class ConnectionFlow:
    def build_connection_presentation(self,layout):
        self._connection_state='idle';self._session_started=None
        row=QHBoxLayout();self.session_device=QLabel('Nenhuma sessão ativa');self.session_device.setTextFormat(Qt.TextFormat.PlainText)
        self.session_device.setObjectName('sessionDevice');row.addWidget(self.session_device)
        self.session_badge=QLabel('Pronto');self.session_badge.setObjectName('sessionBadge');row.addWidget(self.session_badge);row.addStretch()
        self.session_elapsed=QLabel('');self.session_elapsed.setObjectName('muted');row.addWidget(self.session_elapsed);layout.insertLayout(1,row)
        self.connection_overlay=ConnectionOverlay(self);self.fullscreen_tools=FullscreenBar(self)
        self.session_clock=QTimer(self);self.session_clock.setInterval(1000);self.session_clock.timeout.connect(self.update_session_clock);self.session_clock.start()
        self.show_connection_state('idle')

    def connection_display_name(self):
        from .saved_connections import list_connections
        from .device_address import format_address
        if self.active_saved_id:
            entry=next((e for e in list_connections(self.identity) if e['id']==self.active_saved_id),None)
            if entry:return entry['name']
        try:return format_address(self._desk_last_remote)
        except (ValueError,ProtocolError):return 'Computador remoto'

    def show_connection_state(self,state,detail=''):
        if not hasattr(self,'connection_overlay'):return
        self._connection_state=state;overlay=self.connection_overlay
        states={
            'idle':('Sua próxima conexão','Digite o endereço remoto na barra acima para começar.','Nova conexão','Pronto'),
            'locating':('Localizando o computador','Consultando o endereço na rede Desk.','Cancelar','Localizando'),
            'connecting':('Conectando','Preparando o canal de conexão com o outro computador.','Cancelar','Conectando'),
            'approval':('Aguardando autorização','O outro computador precisa aceitar a solicitação e escolher as permissões.','Cancelar','Aguardando aceite'),
            'authenticating':('Verificando acesso autorizado','Confirmando a autorização deste dispositivo.','Cancelar','Verificando acesso'),
            'receiving':('Recebendo a tela','A sessão foi aprovada. Aguardando a primeira imagem.','Desconectar','Conectado'),
            'active':('','','Desconectar','Conectado'),
            'sharing':('Você está compartilhando sua tela','A sessão está ativa. Você pode encerrar o acesso a qualquer momento.','Parar compartilhamento','Compartilhando'),
            'reconnecting':('Reconectando','A conexão foi interrompida. O Desk tentará novamente.','Cancelar','Reconectando'),
            'failed':('Não foi possível conectar','Confira se o outro computador está ligado, conectado e com o Desk aberto.','Tentar novamente','Falha na conexão'),
            'cancelled':('Conexão cancelada','A tentativa foi encerrada. O aviso remoto é retirado assim que a outra ponta recebe a desconexão.','Tentar novamente','Cancelado'),
            'ended':('Sessão encerrada','A transmissão foi encerrada. Você pode conectar novamente quando precisar.','Conectar novamente','Desconectado')}
        title,message,action,badge=states[state]
        overlay.device.setText('Este computador' if state=='sharing' else self.connection_display_name())
        overlay.title.setText(title);overlay.detail.setText(detail or message);overlay.primary.setText(action)
        busy=state in ('locating','connecting','approval','authenticating','receiving','reconnecting')
        overlay.progress.setVisible(busy);overlay.back.setVisible(not busy and state!='idle')
        overlay.setVisible(state!='active');overlay.raise_()
        self.session_device.setText('Este computador' if state=='sharing' else self.connection_display_name() if state!='idle' else 'Nenhuma sessão ativa')
        self.session_badge.setText(badge);self.session_badge.setProperty('connected',state in ('active','receiving','sharing'))
        self.session_badge.style().unpolish(self.session_badge);self.session_badge.style().polish(self.session_badge)
        self.remote_invite.setReadOnly(bool(self.connecting or self.peer))
        self.session_close.setEnabled(bool(self.connecting or self.peer or self.retry_timer.isActive()))
        if state not in ('active','receiving','sharing'):self._session_started=None;self.session_elapsed.clear()
        self.update_session_actions()

    def connection_primary_action(self):
        if self._connection_state=='idle':self.connection_go_home()
        elif self._connection_state in ('locating','connecting','approval','authenticating','receiving','sharing','reconnecting'):self.disconnect()
        else:
            if self.peer or self.connecting:return
            self.next_saved_id=self.active_saved_id;self.connect_peer()

    def connection_go_home(self):
        if self.connecting:self.disconnect()
        self.tabs.setCurrentIndex(0);self.remote_invite.setFocus();self.remote_invite.selectAll()

    def update_session_clock(self):
        if self._session_started is None:return
        seconds=max(0,int(time.monotonic()-self._session_started));hours,seconds=divmod(seconds,3600);minutes,seconds=divmod(seconds,60)
        self.session_elapsed.setText(f'{hours:02d}:{minutes:02d}:{seconds:02d}')

    def on_connection_event(self,name,data):
        if name=='connect_stage' and data.get('epoch')==self.connection_epoch:
            self.show_connection_state(data.get('stage','connecting'),data.get('text',''))
        elif name=='connected' and self.peer:
            self._session_started=time.monotonic();self.update_session_clock()
            self.show_connection_state('sharing' if self.peer.role=='host' else 'receiving')
            self.session_nav.setText('Compartilhamento' if self.peer.role=='host' else self.connection_display_name())
            if self.peer.role=='viewer' and self.start_fullscreen.isChecked():
                QTimer.singleShot(0,lambda epoch=self.connection_epoch:self.begin_preferred_fullscreen(epoch))
        elif name=='connect_error':
            self.show_connection_state('reconnecting' if self.retry_timer.isActive() else 'failed',data.get('text',''))
        elif name=='disconnected':
            self.canvas.image=None;self.canvas.allow_control=False;self.canvas.update()
            self.show_connection_state('reconnecting' if self.retry_timer.isActive() else 'ended',data.get('text',''))


STYLE='''
QWidget#connectionOverlay {background:#151515;}
QFrame#connectionCard {background:#242424;border:1px solid #454545;border-radius:5px;}
QFrame#connectionCard QLabel {background:transparent;}
QLabel#connectionDevice {font-size:15px;color:#ec756b;}
QLabel#connectionHeading {font-size:24px;font-weight:600;}
QProgressBar {background:#353535;border:0;border-radius:2px;}
QProgressBar::chunk {background:#ec6359;}
QLabel#sessionDevice {font-weight:600;}
QLabel#sessionBadge {background:#39312f;color:#d9b6ae;border-radius:3px;padding:3px 9px;}
QLabel#sessionBadge[connected="true"] {background:#284334;color:#a1d5ae;}
QFrame#fullscreenBar {background:#262626;border:1px solid #555;border-bottom-left-radius:5px;border-bottom-right-radius:5px;}
QFrame#fullscreenBar QLabel {background:transparent;}
QFrame#fullscreenBar QPushButton {padding:6px 10px;}
'''
