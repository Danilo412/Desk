"""Desk's address-first desktop shell; transport and consent remain independent."""
from __future__ import annotations
import os,time,socket,math
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSize,QRectF,QEvent,QPointF,Signal,QUrl
from PySide6.QtGui import QIcon,QAction,QKeySequence,QShortcut,QPainter,QColor,QPen,QPolygonF,QLinearGradient,QDesktopServices
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QToolButton,QLineEdit,
    QPlainTextEdit,QCheckBox,QComboBox,QVBoxLayout,QHBoxLayout,QGridLayout,QTabWidget,
    QMenu,QApplication,QScrollArea,QListWidget,QListWidgetItem,QListView,QAbstractItemView,
    QStyle,QDialog,QDialogButtonBox,QStyledItemDelegate,QSplitter,QStackedWidget,QWidgetAction,QInputDialog,QMessageBox)
from .device_address import format_address,normalize_address
from .wire import ProtocolError
from .connection_ui import ConnectionFlow,STYLE as CONNECTION_STYLE
from .session_tools import SessionTools
from .collaboration_ui import CollaborationTools,SessionChat,TransferPanel,FileDropArea
from .image_controls import ImageControls,STYLE as IMAGE_STYLE
from .advanced_ui import AdvancedTools

ASSETS=Path(__file__).resolve().parents[2]/'assets'

class AddressField(QLineEdit):
    # Keep the existing connection API and saved-profile compatibility.
    def toPlainText(self):return self.text()
    def setPlainText(self,value):self.setText(value)

class CopyAddressField(QLineEdit):
    copyRequested=Signal()
    COPY_HINT='Clique para copiar seu endereço · Ctrl+Shift+C'

    def __init__(self):
        super().__init__();self._press_position=None;self._dragged=False
        self.setReadOnly(True);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.COPY_HINT);self.setAccessibleDescription('Clique ou pressione Enter para copiar seu endereço Desk.')

    def mousePressEvent(self,event):
        self._press_position=event.position().toPoint() if event.button()==Qt.MouseButton.LeftButton else None
        self._dragged=False;super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._press_position is not None and (event.position().toPoint()-self._press_position).manhattanLength()>=QApplication.startDragDistance():self._dragged=True
        super().mouseMoveEvent(event);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self,event):
        copy=event.button()==Qt.MouseButton.LeftButton and self._press_position is not None and not self._dragged and (event.position().toPoint()-self._press_position).manhattanLength()<QApplication.startDragDistance() and self.rect().contains(event.position().toPoint())
        self._press_position=None;super().mouseReleaseEvent(event)
        if copy and self.text().strip():self.copyRequested.emit()

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space) and event.modifiers()==Qt.KeyboardModifier.NoModifier:
            if self.text().strip():self.copyRequested.emit()
            event.accept();return
        super().keyPressEvent(event)

    def set_copied(self,copied):
        self.setProperty('copied',bool(copied));self.setToolTip('Endereço copiado' if copied else self.COPY_HINT)
        self.style().unpolish(self);self.style().polish(self);self.update()

def action_button(text,callback,primary=False):
    b=QPushButton(text);b.clicked.connect(callback)
    if primary:b.setObjectName('primary')
    return b

def hint(text):
    label=QLabel(text);label.setWordWrap(True);label.setObjectName('muted');return label

class TileGrid(QWidget):
    """Keep the shortcuts readable when the window is narrower."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0)
        self.grid.setSpacing(10);self.tiles=[];self.columns=0

    def add_tile(self,tile):
        self.tiles.append(tile);self.reflow()

    def reflow(self):
        columns=4 if self.width()>=1100 else 2
        if columns==self.columns and self.grid.count()==len(self.tiles):return
        while self.grid.count():self.grid.takeAt(0)
        self.columns=columns
        for i,tile in enumerate(self.tiles):self.grid.addWidget(tile,i//columns,i%columns)
        for i in range(4):self.grid.setColumnStretch(i,1 if i<columns else 0)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

class QuickActionCard(QPushButton):
    """A whole-card native button: one click target and one keyboard action."""
    def __init__(self,title,description,action,handler,color):
        super().__init__();self.setObjectName('featureTile');self.clicked.connect(handler)
        self.setAccessibleName(title+' · '+action);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QPushButton#featureTile {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 '+color+',stop:1 #29282c);}')
        col=QVBoxLayout(self);col.setContentsMargins(17,16,17,13);col.setSpacing(9)
        for text,name in [(title,'tileTitle'),(description,'tileDescription')]:
            label=QLabel(text);label.setWordWrap(True);label.setObjectName(name)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);col.addWidget(label)
        col.addStretch();label=QLabel(action+'  →');label.setObjectName('tileAction')
        label.setAlignment(Qt.AlignmentFlag.AlignRight);label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);col.addWidget(label)
        self.setMinimumHeight(156)

class DeviceCardDelegate(QStyledItemDelegate):
    """Draw original device cards; never imply an unverified online state."""
    def paint(self,painter,option,index):
        if self.parent().viewMode()!=QListView.ViewMode.IconMode:
            return super().paint(painter,option,index)
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(3,3,-5,-5)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        data=index.data(Qt.ItemDataRole.UserRole)
        color=QColor(data.get('color','#35485b') if isinstance(data,dict) else '#303a45')
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,color.lighter(135));gradient.setColorAt(.6,color);gradient.setColorAt(1,QColor('#1d252e'))
        painter.setBrush(gradient);painter.setPen(QPen(QColor('#ef6b61' if selected else '#5b6875'),1))
        painter.drawRoundedRect(rect,3,3)
        empty=not isinstance(data,dict)
        display=str(index.data(Qt.ItemDataRole.DisplayRole) or '').split('\n')
        title=display[0];subtitle=' · '.join(display[1:])
        painter.setPen(QPen(QColor('#b4c2cd' if empty else '#e5edf3'),2))
        monitor=QRectF(rect.left()+16,rect.top()+17,34,22)
        painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(monitor,2,2)
        x=monitor.center().x();y=monitor.bottom()
        painter.drawLine(int(x),int(y),int(x),int(y+7));painter.drawLine(int(x-10),int(y+7),int(x+10),int(y+7))
        if not empty and (data.get('id') or data.get('favorite_id') or data.get('fixed')):
            filled=bool(data.get('id') or data.get('favorite_id'))
            painter.setPen(QPen(QColor('#efc871' if filled else '#cbd3da'),1.2));painter.setBrush(QColor('#efc871') if filled else Qt.BrushStyle.NoBrush)
            cx=rect.right()-22;cy=rect.top()+22
            star=QPolygonF([QPointF(cx+math.cos(-math.pi/2+i*math.pi/5)*(8 if i%2==0 else 3.5),cy+math.sin(-math.pi/2+i*math.pi/5)*(8 if i%2==0 else 3.5)) for i in range(10)])
            painter.drawPolygon(star);painter.setBrush(Qt.BrushStyle.NoBrush)
        band=QLinearGradient(0,rect.top()+57,0,rect.bottom());band.setColorAt(0,QColor(15,20,26,0));band.setColorAt(1,QColor(15,20,26,220))
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(band);painter.drawRect(rect.adjusted(1,57,-1,-1))
        font=option.font;font.setPointSize(11);font.setBold(True);painter.setFont(font)
        painter.setPen(QColor('#e9eef2' if not empty else '#a9b6c1'))
        painter.drawText(QRectF(rect.left()+15,rect.top()+64,rect.width()-30,25),Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,int(rect.width()-30)))
        font.setPointSize(9);font.setBold(False);painter.setFont(font);painter.setPen(QColor('#b6c1ca'))
        painter.drawText(QRectF(rect.left()+15,rect.top()+94,rect.width()-30,40),Qt.TextFlag.TextWordWrap,subtitle)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor('#ed6960'),1,Qt.PenStyle.DotLine));painter.drawRoundedRect(rect.adjusted(3,3,-3,-3),2,2)
        painter.restore()

    def editorEvent(self,event,model,option,index):
        if self.parent().viewMode()==QListView.ViewMode.IconMode and event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            rect=QRectF(option.rect).adjusted(3,3,-5,-5)
            data=index.data(Qt.ItemDataRole.UserRole)
            if isinstance(data,dict) and (data.get('id') or data.get('favorite_id') or data.get('fixed')) and QRectF(rect.right()-38,rect.top()+5,32,34).contains(event.position()):
                self.parent().window().favorite_star_clicked(self.parent().itemFromIndex(index));return True
        return super().editorEvent(event,model,option,index)

class DeskShell(ConnectionFlow,SessionTools,CollaborationTools,ImageControls,AdvancedTools):
    def build_shell(self):
        self._desk_listening_requested=True;self._desk_copy_when_ready=False
        self._desk_address_online=False
        self._image_panels=[]
        self._desk_last_remote='';self._desk_recent=list(self.identity.settings().get('desk_recents',[]))[:20]
        self._desk_device_view=self.identity.settings().get('desk_device_view','cards')
        self._desk_copy_reset=QTimer(self);self._desk_copy_reset.setSingleShot(True)
        self._desk_copy_reset.timeout.connect(self.reset_copy_feedback)
        self.address_timer=QTimer(self);self.address_timer.setSingleShot(True)
        self.address_timer.timeout.connect(self.renew_address)
        self.setWindowTitle('Desk');self.resize(1280,840);self.setMinimumSize(980,680)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.setWindowIcon(QIcon(str(ASSETS/'desk.ico')))
        body=QWidget();self.setCentralWidget(body);outer=QVBoxLayout(body)
        outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        from .window_chrome import DeskTitleStrip
        header=DeskTitleStrip(self);row=QHBoxLayout(header)
        row.setContentsMargins(12,3,12,3);row.setSpacing(8)
        mark=QLabel();mark.setPixmap(QIcon(str(ASSETS/'desk.ico')).pixmap(20,20));row.addWidget(mark)
        brand=QLabel('Desk');brand.setObjectName('brand');row.addWidget(brand)
        self.home_nav=action_button('Nova conexão',lambda:self.tabs.setCurrentIndex(0));self.home_nav.setIcon(QIcon(str(ASSETS/'monitor.svg')));self.home_nav.setObjectName('navTab');row.addWidget(self.home_nav)
        self.session_nav=action_button('Sessão',lambda:self.tabs.setCurrentIndex(1));self.session_nav.setObjectName('navTab');row.addWidget(self.session_nav)
        self.session_close=QToolButton();self.session_close.setText('×');self.session_close.setAccessibleName('Encerrar sessão');self.session_close.setToolTip('Cancelar conexão ou encerrar a sessão');self.session_close.clicked.connect(self.disconnect);self.session_close.setEnabled(False);row.addWidget(self.session_close)
        plus=QToolButton();plus.setText('+');plus.setToolTip('Nova conexão · Ctrl+L');plus.clicked.connect(self.focus_remote_address);row.addWidget(plus)
        row.addStretch()
        self.update_available_button=QPushButton('Atualização disponível');self.update_available_button.setObjectName('outlineAccent');self.update_available_button.hide()
        self.update_available_button.clicked.connect(lambda:self.updates.show_offer());row.addWidget(self.update_available_button)
        self.status=QLabel('Pronto para conectar');self.status.setObjectName('status');row.addWidget(self.status)
        header.add_window_controls(row)
        outer.addWidget(header)
        bar=QFrame();bar.setObjectName('addressBar');line=QHBoxLayout(bar)
        line.setContentsMargins(12,4,12,4);line.setSpacing(8)
        self.availability_dot=QLabel('●');self.availability_dot.setObjectName('onlineDot');line.addWidget(self.availability_dot)
        self.remote_invite=AddressField();self.remote_invite.setObjectName('remoteAddress')
        self.remote_invite.setPlaceholderText('Digite o endereço remoto');self.remote_invite.setMaxLength(20000)
        self.remote_invite.setAccessibleName('Endereço remoto Desk')
        self.remote_invite.returnPressed.connect(self.connect_peer);line.addWidget(self.remote_invite,1)
        paste=QToolButton();paste.setIcon(QIcon(str(ASSETS/'paste.svg')));paste.setToolTip('Colar endereço');paste.setAccessibleName('Colar endereço remoto')
        paste.clicked.connect(self.paste_address);line.addWidget(paste)
        self.connect_button=action_button('Conectar  →',self.connect_peer,True);line.addWidget(self.connect_button)
        more=QToolButton();more.setIcon(QIcon(str(ASSETS/'menu.svg')));more.setIconSize(QSize(20,20));more.setAccessibleName('Menu Desk');more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(more)
        menu.addAction('Nova conexão',self.focus_remote_address)
        menu.addAction('Favoritos',lambda:self.open_device_section(1))
        menu.addAction('Sessões recentes',lambda:self.open_device_section(2))
        menu.addSeparator()
        for label,index in [('Sessão',1),('Gerenciar acessos salvos',3),('Configurações',2),('Sobre o Desk',4)]:
            a=menu.addAction(label);a.triggered.connect(lambda checked=False,i=index:self.tabs.setCurrentIndex(i))
        menu.addAction('Verificar atualizações',lambda:self.open_update_settings(True))
        menu.addSeparator();menu.addAction('Sair do Desk',self.quit_application);more.setMenu(menu);line.addWidget(more)
        outer.addWidget(bar)
        self.tabs=QTabWidget();self.tabs.setObjectName('workspace');self.tabs.tabBar().hide();outer.addWidget(self.tabs,1)
        self._build_home();self._build_session();self._build_network();self._build_saved();self._build_about()
        self.build_advanced_tools(menu)
        self.relay_config.setEchoMode(QLineEdit.EchoMode.Password)
        self.tabs.currentChanged.connect(self.workspace_changed)
        self.workspace_changed(0)
        from .ui_motion import InterfaceMotion
        self.interface_motion=InterfaceMotion(self,self.identity.settings().get('interface_motion',True))
        self.remote_invite.textChanged.connect(self.remote_address_changed)
        self.remote_address_changed()
        self.set_availability('preparing')
        self.address_shortcuts=[]
        for keys,callback in [('Ctrl+L',self.focus_remote_address),('Ctrl+Shift+C',self.copy_invite)]:
            shortcut=QShortcut(QKeySequence(keys),self);shortcut.activated.connect(callback);self.address_shortcuts.append(shortcut)
        if os.environ.get('NOVOACESSO_OFFLINE')!='1' and os.environ.get('DESK_AUTOREADY','1')!='0':
            QTimer.singleShot(500,self.prepare_address)

    def workspace_changed(self,index):
        self.home_nav.setProperty('selected',index==0);self.session_nav.setProperty('selected',index==1)
        for b in (self.home_nav,self.session_nav):b.style().unpolish(b);b.style().polish(b)
        if hasattr(self,'interface_motion'):self.interface_motion.select_page(index)
        self.mark_chat_read()

    def build_session_page(self):
        from .app import RemoteCanvas
        from .quality import PROFILES
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(12,10,12,8);layout.setSpacing(8)
        toolbar=QFrame();toolbar.setObjectName('sessionToolbar');row=QHBoxLayout(toolbar)
        row.setContentsMargins(10,6,10,6);row.setSpacing(8)
        self.monitor=QComboBox(toolbar);self.monitor.setPlaceholderText('Monitor remoto');self.monitor.setAccessibleName('Selecionar monitor remoto');self.monitor.hide()
        self.monitor_picker=QToolButton();self.monitor_picker.setText('Monitores');self.monitor_picker.setObjectName('sessionTool');self.monitor_picker.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.monitor_picker.setAccessibleName('Selecionar tela remota');self.monitor_picker.setMenu(self.make_monitor_menu(self.monitor_picker));row.addWidget(self.monitor_picker)
        self.image_menu_button=QToolButton();self.image_menu_button.setText('Imagem');self.image_menu_button.setIcon(QIcon(str(ASSETS/'monitor.svg')))
        self.image_menu_button.setObjectName('sessionTool')
        self.image_menu_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.image_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.image_menu_button.setAccessibleName('Opções de imagem e qualidade')
        image_menu=QMenu(self.image_menu_button)
        self.display=QComboBox(toolbar);self.display.addItem('Ajustar à janela','fit');self.display.addItem('Tamanho real · 100%','original');self.display.addItem('Preencher a tela','stretch')
        self.quality=QComboBox(toolbar)
        for label,width,fps in PROFILES:self.quality.addItem(label,(width,fps))
        self.codec=QComboBox(toolbar);self.codec.addItem('Automático · texto nítido','auto');self.codec.addItem('Sem perda · mais tráfego','deflate');self.codec.addItem('Vídeo · movimento contínuo','vp8')
        self.start_fullscreen=QCheckBox(toolbar)
        for widget in (self.display,self.quality,self.codec,self.start_fullscreen):widget.hide()
        self.image_options=self.make_image_panel(compact=True)
        widget_action=QWidgetAction(image_menu);widget_action.setDefaultWidget(self.image_options);image_menu.addAction(widget_action)
        self.image_menu_button.setMenu(image_menu);row.addWidget(self.image_menu_button)
        self.files_toolbar_button=action_button('Arquivos',lambda:self.open_session_panel(1));self.files_toolbar_button.setObjectName('sessionTool');row.addWidget(self.files_toolbar_button)
        self.session_tools_button=QToolButton();self.session_tools_button.setText('Ferramentas');self.session_tools_button.setIcon(QIcon(str(ASSETS/'tools.svg')));self.session_tools_button.setObjectName('sessionTool');self.session_tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.session_tools_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tools_menu=QMenu(self.session_tools_button);tools_menu.addAction('Conversa',lambda:self.open_session_panel(0))
        self.file_menu_action=tools_menu.addAction('Enviar arquivo…',self.send_file)
        self.save_menu_action=tools_menu.addAction('Salvar este computador',self.save_current_computer)
        tools_menu.addAction('Permissões da sessão',lambda:self.open_session_panel(2));self.session_tools_button.setMenu(tools_menu);row.addWidget(self.session_tools_button)
        self.session_info_button=QToolButton();self.session_info_button.setIcon(QIcon(str(ASSETS/'info.svg')));self.session_info_button.setIconSize(QSize(19,19))
        self.session_info_button.setAccessibleName('Informações da sessão');self.session_info_button.setToolTip('Conexão, imagem e permissões');self.session_info_button.clicked.connect(self.show_session_information);row.addWidget(self.session_info_button)
        self.control=QCheckBox('Mouse e teclado');row.addWidget(self.control);row.addStretch()
        self.session_sidebar_button=QPushButton('Conversa');self.session_sidebar_button.setToolTip('Conversa, arquivos e acesso salvo');self.session_sidebar_button.setCheckable(True)
        row.addWidget(self.session_sidebar_button)
        self.fullscreen_button=action_button('Tela cheia',self.fullscreen);self.fullscreen_button.setToolTip('Expandir somente a tela remota · Esc para voltar');row.addWidget(self.fullscreen_button)
        self.fullscreen_button.setIcon(QIcon(str(ASSETS/'fullscreen.svg')))
        self.disconnect_button=action_button('Desconectar',self.disconnect);self.disconnect_button.setObjectName('dangerOutline');row.addWidget(self.disconnect_button)
        layout.addWidget(toolbar)
        self.control_hint=hint('O controle fica disponível quando o computador remoto autoriza mouse e teclado.');layout.addWidget(self.control_hint)
        self.session_split=QSplitter();self.session_split.setChildrenCollapsible(False)
        self.canvas=RemoteCanvas();self.canvas.input_event.connect(self.send_input);self.canvas.exit_requested.connect(self.exit_fullscreen)
        self.canvas.files_dropped.connect(self.send_paths)
        self.viewer=QScrollArea();self.viewer.setWidget(self.canvas);self.viewer.setWidgetResizable(True);self.session_split.addWidget(self.viewer)
        self.session_side=QTabWidget();self.session_side.setObjectName('sessionSide');self.session_side.setMinimumWidth(280);self.session_side.setMaximumWidth(370)
        chat_page=QWidget();chat_layout=QVBoxLayout(chat_page);chat_layout.setContentsMargins(12,12,12,12)
        self.chat=SessionChat();self.chat.setReadOnly(True);self.chat.setMaximumBlockCount(400);self.chat.setAccessibleName('Histórico da conversa');chat_layout.addWidget(self.chat,1)
        self.message=QLineEdit();self.message.setPlaceholderText('Digite uma mensagem');self.message.setMaxLength(4000);self.message.returnPressed.connect(self.send_chat);chat_layout.addWidget(self.message)
        self.send_message_button=action_button('Enviar mensagem',self.send_chat,True);chat_layout.addWidget(self.send_message_button)
        self.session_side.addTab(chat_page,'Conversa')
        files_page=QWidget();files=QVBoxLayout(files_page);files.setContentsMargins(14,16,14,14)
        files.addWidget(hint('Envie arquivos ou pastas pelo Desk. A outra ponta escolhe onde salvar.'))
        self.file_drop_area=FileDropArea();self.file_drop_area.files_dropped.connect(self.send_paths);files.addWidget(self.file_drop_area)
        self.send_file_button=action_button('Enviar arquivos…',self.send_file);files.addWidget(self.send_file_button)
        self.files_folder_button=action_button('Enviar pasta…',self.send_folder_dialog);files.addWidget(self.files_folder_button)
        self.paste_files_button=action_button('Colar arquivos',self.paste_files);files.addWidget(self.paste_files_button)
        self.send_clipboard_button=action_button('Enviar texto copiado',self.send_clipboard);files.addWidget(self.send_clipboard_button)
        self.sync_clipboard=QCheckBox('Sincronizar texto copiado');self.sync_clipboard.setToolTip('Requer a permissão concedida pelo computador compartilhado.');files.addWidget(self.sync_clipboard)
        self.transfer_panel=TransferPanel();files.addWidget(self.transfer_panel,1)
        self.session_side.addTab(files_page,'Arquivos')
        access_page=QWidget();access=QVBoxLayout(access_page);access.setContentsMargins(14,16,14,14)
        access.addWidget(hint('Guarde um acesso já autorizado para voltar a este computador.'))
        self.save_computer_button=action_button('Salvar este computador',self.save_current_computer);access.addWidget(self.save_computer_button)
        self.authorize_reconnect_button=action_button('Autorizar reconexão…',self.enable_saved_access)
        self.authorize_reconnect_button.setToolTip('Permitir reconexão deste dispositivo após confirmação')
        access.addWidget(self.authorize_reconnect_button)
        self.auto_reconnect=QCheckBox('Reconectar automaticamente');self.auto_reconnect.setChecked(True);access.addWidget(self.auto_reconnect)
        self.permissions_label=hint('Sem sessão ativa');access.addWidget(self.permissions_label);access.addStretch();self.session_side.addTab(access_page,'Acesso')
        self.session_split.addWidget(self.session_side);self.session_split.setStretchFactor(0,1);layout.addWidget(self.session_split,1)
        self.metrics=hint('Aguardando transmissão.');layout.addWidget(self.metrics)
        self.monitor.currentIndexChanged.connect(self.change_view);self.codec.currentIndexChanged.connect(self.change_view);self.quality.currentIndexChanged.connect(self.change_view)
        self.monitor.currentIndexChanged.connect(self.refresh_monitor_tools)
        self.start_fullscreen.toggled.connect(self.change_view)
        self.display.currentIndexChanged.connect(self.change_display);self.control.stateChanged.connect(self.control_changed);self.auto_reconnect.toggled.connect(self.change_view)
        self.session_sidebar_button.toggled.connect(self.toggle_session_sidebar)
        self._unread_chat=0;self.session_side.currentChanged.connect(self.mark_chat_read)
        visible=self.identity.settings().get('desk_session_sidebar',True)
        self.session_sidebar_button.setChecked(visible);self.session_side.setVisible(visible)
        self.tabs.addTab(page,'Sessão');self.build_connection_presentation(layout);self.update_session_actions()

    def open_session_panel(self,index):
        self.exit_fullscreen()
        self.session_sidebar_button.setChecked(True);self.session_side.setCurrentIndex(index)
        self.mark_chat_read()

    def toggle_session_sidebar(self,visible):
        self.session_side.setVisible(visible)
        self.identity.configure(desk_session_sidebar=visible)
        if visible and self.peer and self.canvas.allow_control:self.message.setFocus()
        self.mark_chat_read()

    def update_session_actions(self):
        connected=bool(self.peer)
        self.canvas.transfer_enabled=connected
        for widget in (self.files_toolbar_button,self.file_drop_area,self.files_folder_button,self.paste_files_button):widget.setEnabled(connected)
        for button in (self.send_message_button,self.send_file_button,self.send_clipboard_button,self.authorize_reconnect_button):button.setEnabled(connected)
        self.save_computer_button.setEnabled(connected and bool(self.available_profile or self.last_connection_profile))
        self.disconnect_button.setEnabled(connected or self.connecting or bool(self.retry_timer.isActive()))
        self.file_menu_action.setEnabled(connected);self.save_menu_action.setEnabled(self.save_computer_button.isEnabled())
        remote_view=not connected or getattr(self.peer,'role','')=='viewer'
        self.monitor.setEnabled(remote_view);self.image_menu_button.setEnabled(remote_view)
        self.session_info_button.setEnabled(connected);self.refresh_monitor_tools()
        self.update_advanced_actions()

    def build_settings_page(self,settings,saved_config,cloud_key):
        page=QWidget();layout=QHBoxLayout(page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.settings_navigation=QListWidget();self.settings_navigation.setObjectName('settingsNavigation');self.settings_navigation.setFixedWidth(220)
        self.settings_navigation.setAccessibleName('Categorias de configurações')
        self.settings_navigation.addItems(['Conexão','Acesso sem supervisão','Dispositivos autorizados'])
        sidebar=QWidget();sidebar.setObjectName('settingsSidebar');side=QVBoxLayout(sidebar);side.setContentsMargins(0,18,0,0);side.setSpacing(10)
        title=QLabel('Configurações');title.setObjectName('settingsTitle');side.addWidget(title)
        side.addWidget(self.settings_navigation,1);layout.addWidget(sidebar);self.settings_pages=QStackedWidget();layout.addWidget(self.settings_pages,1)
        def section(title,description):
            body=QWidget();col=QVBoxLayout(body);col.setContentsMargins(28,24,28,24);col.setSpacing(14)
            heading=QLabel(title);heading.setObjectName('settingsHeading');col.addWidget(heading);col.addWidget(hint(description))
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);self.settings_pages.addWidget(scroll);return col
        connection=section('Conexão','O Desk prepara a conexão pela internet ao abrir. Mantenha a mesma configuração nos computadores que você usa.')
        self.use_relay=QCheckBox('Usar serviço de conexão pela internet');self.use_relay.setChecked(settings.get('use_relay',bool(cloud_key)));connection.addWidget(self.use_relay)
        self.force_relay=QCheckBox('Forçar relay público · sem conexão direta');self.force_relay.setChecked(bool(settings.get('force_relay',False) or os.environ.get('DESK_FORCE_RELAY')=='1'));connection.addWidget(self.force_relay)
        connection.addWidget(hint('Use para testar redes que exigem retransmissão. Se o TURN não estiver disponível, a conexão falha; não volta silenciosamente para a rota direta. Desmarque para permitir a escolha automática da rota.'))
        self.relay_test_button=action_button('Testar conexão com o relay',self.test_relay);connection.addWidget(self.relay_test_button,0,Qt.AlignmentFlag.AlignLeft)
        self.relay_test_status=hint('');connection.addWidget(self.relay_test_status)
        connection.addWidget(action_button('Importar configuração de conexão…',self.import_network_configuration),0,Qt.AlignmentFlag.AlignLeft)
        advanced=QToolButton();advanced.setText('Configuração avançada');advanced.setCheckable(True);advanced.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        advanced.setArrowType(Qt.ArrowType.RightArrow);connection.addWidget(advanced,0,Qt.AlignmentFlag.AlignLeft)
        advanced_box=QWidget();advanced_layout=QVBoxLayout(advanced_box);advanced_layout.setContentsMargins(0,0,0,0)
        advanced_layout.addWidget(hint('Altere apenas se precisar substituir o serviço de conexão. As condições e a franquia dependem do provedor.'))
        self.relay_config=QLineEdit(saved_config or cloud_key);self.relay_config.setEchoMode(QLineEdit.EchoMode.Password);self.relay_config.setPlaceholderText('Configuração de conexão');self.relay_config.setAccessibleName('Configuração privada de conexão');advanced_layout.addWidget(self.relay_config)
        from .ui_motion import reveal_widget
        advanced_box.hide();advanced.toggled.connect(lambda on:reveal_widget(advanced_box,on,self));advanced.toggled.connect(lambda on:advanced.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow));connection.addWidget(advanced_box)
        connection.addWidget(action_button('Salvar configuração de conexão',self.apply_network),0,Qt.AlignmentFlag.AlignLeft);connection.addStretch()
        access=section('Acesso sem supervisão','Somente dispositivos autorizados podem voltar sem uma nova solicitação de aceite.')
        self.unattended=QCheckBox('Habilitar acesso permanente por dispositivos autorizados');self.unattended.setChecked(settings.get('unattended',False));self.unattended.toggled.connect(self.unattended_changed);access.addWidget(self.unattended)
        self.autostart=QCheckBox('Iniciar com o Windows, após meu login');self.autostart.setChecked(settings.get('autostart',False));self.autostart.toggled.connect(self.autostart_changed);access.addWidget(self.autostart)
        self.unattended_files=QCheckBox('Receber arquivos autorizados em Downloads sem pedir destino');self.unattended_files.setChecked(settings.get('unattended_files',False));self.unattended_files.toggled.connect(lambda enabled:self.identity.configure(unattended_files=enabled));access.addWidget(self.unattended_files)
        access.addWidget(hint('Faça uma sessão aprovada antes de autorizar um dispositivo. O Desk pede confirmação para ativar o acesso permanente.'))
        self.permanent_profile=QPlainTextEdit();self.permanent_profile.setReadOnly(True);self.permanent_profile.setMaximumHeight(100);self.permanent_profile.setPlaceholderText('O perfil aparece ao habilitar o acesso permanente. Compartilhe somente com o dispositivo autorizado.');access.addWidget(self.permanent_profile)
        access.addWidget(action_button('Copiar perfil permanente',lambda:QApplication.clipboard().setText(self.permanent_profile.toPlainText())),0,Qt.AlignmentFlag.AlignLeft);access.addStretch()
        devices=section('Dispositivos autorizados','Confira os dispositivos com permissão para reconectar e revogue os que não usa mais.')
        devices.addWidget(action_button('Autorizar dispositivo da sessão',self.trust_current),0,Qt.AlignmentFlag.AlignLeft)
        self.trusted_devices=QListWidget();self.trusted_devices.setAccessibleName('Dispositivos autorizados para acesso permanente');devices.addWidget(self.trusted_devices,1)
        devices.addWidget(action_button('Revogar dispositivo selecionado',self.revoke_current),0,Qt.AlignmentFlag.AlignLeft)
        self.settings_navigation.addItem('Imagem')
        image=section('Imagem','Escolha a qualidade e como a tela remota será exibida. As preferências são guardadas para os próximos acessos.')
        image.addWidget(self.make_image_panel());image.addStretch()
        self.settings_navigation.addItem('Aparência')
        appearance=section('Aparência','Ajuste a resposta visual da interface do Desk.')
        self.motion_enabled=QCheckBox('Animações discretas da interface')
        self.motion_enabled.setChecked(settings.get('interface_motion',True));appearance.addWidget(self.motion_enabled)
        appearance.addWidget(hint('Realce suave dos botões e transição entre abas. Respeita a preferência de animações do Windows.'))
        def change_motion(enabled):
            self.identity.configure(interface_motion=enabled)
            if hasattr(self,'interface_motion'):self.interface_motion.set_requested(enabled)
        self.motion_enabled.toggled.connect(change_motion);appearance.addStretch()
        self.settings_navigation.addItem('Notificações')
        notifications=section('Notificações','Receba avisos de mensagens, arquivos e solicitações mesmo usando outro aplicativo.')
        for key,label in [('notifications_enabled','Mostrar notificações de mensagens e arquivos'),('notification_previews','Mostrar prévia das mensagens'),('foreground_requests','Trazer pedidos de conexão e arquivos para a frente')]:
            box=QCheckBox(label);box.setChecked(settings.get(key,True));box.toggled.connect(lambda enabled,k=key:self.identity.configure(**{k:enabled}));notifications.addWidget(box)
        notifications.addWidget(hint('Mensagens mostram um aviso discreto. Pedidos de aceite abrem uma janela acima do Desk e continuam dependendo da sua confirmação.'))
        notifications.addWidget(action_button('Testar mensagem em 5 segundos',lambda:QTimer.singleShot(5000,self.notifications.test_message)),0,Qt.AlignmentFlag.AlignLeft)
        notifications.addWidget(action_button('Testar solicitação em 5 segundos',lambda:QTimer.singleShot(5000,self.notifications.test_request)),0,Qt.AlignmentFlag.AlignLeft);notifications.addStretch()
        self.update_settings_index=self.settings_navigation.count();self.settings_navigation.addItem('Atualizações')
        updates=section('Atualizações','Confira a versão instalada e receba as próximas versões sem reenviar o instalador.')
        from . import __version__
        updates.addWidget(hint('Versão instalada: Desk '+__version__))
        self.update_status_label=hint('Ainda não foi feita uma verificação nesta execução.');updates.addWidget(self.update_status_label)
        self.update_last_check=hint('');updates.addWidget(self.update_last_check)
        self.update_check_button=action_button('Verificar atualizações agora',lambda:self.updates.check(True));updates.addWidget(self.update_check_button,0,Qt.AlignmentFlag.AlignLeft)
        self.update_offer_button=action_button('Ver atualização disponível',lambda:self.updates.show_offer());self.update_offer_button.hide();updates.addWidget(self.update_offer_button,0,Qt.AlignmentFlag.AlignLeft)
        updates.addWidget(action_button('Abrir página de versões',lambda:QDesktopServices.openUrl(QUrl('https://github.com/Danilo412/Desk/releases/latest'))),0,Qt.AlignmentFlag.AlignLeft)
        updates.addWidget(hint('A busca é automática ao abrir e a cada cinco minutos. O download é conferido antes de instalar. Termine a sessão remota para aplicar a atualização; seu número e acessos salvos serão mantidos.'));updates.addStretch()
        for i,icon in enumerate(['connection','lock','monitor','monitor','settings','info','download']):self.settings_navigation.item(i).setIcon(QIcon(str(ASSETS/(icon+'.svg'))))
        self.settings_navigation.currentRowChanged.connect(self.settings_pages.setCurrentIndex);self.settings_navigation.setCurrentRow(0)
        self.settings_page=page;self.tabs.addTab(page,'Configurações');self.refresh_trusted()

    def open_update_settings(self,check=False):
        if self._fullscreen:self.exit_fullscreen()
        self.tabs.setCurrentWidget(self.settings_page);self.settings_navigation.setCurrentRow(self.update_settings_index)
        if check:self.updates.check(True)

    def remote_address_changed(self):
        self.connect_button.setEnabled(bool(self.remote_invite.text().strip()) and not self.connecting and not self.peer)

    def focus_remote_address(self):
        self.tabs.setCurrentIndex(0);self.remote_invite.setFocus();self.remote_invite.selectAll()

    def open_device_section(self,index):
        self.tabs.setCurrentIndex(0);self.home_sections.setCurrentIndex(index)

    def set_availability(self,state):
        colors={'online':'#64c675','active':'#64c675','preparing':'#d6aa5b','offline':'#919191'}
        labels={'online':'Disponível para receber solicitações','active':'Sessão ativa',
                'preparing':'Conectando ao serviço de internet','offline':'Recebimento indisponível'}
        self.availability_dot.setStyleSheet('color:'+colors[state]+';background:transparent;')
        self.availability_dot.setToolTip(labels[state]);self.availability_dot.setAccessibleName(labels[state])

    def reset_copy_feedback(self):
        self.copy_address_button.setIcon(QIcon(str(ASSETS/'copy.svg')))
        self.copy_address_button.setToolTip('Copiar seu endereço · Ctrl+Shift+C')
        self.copy_address_button.setAccessibleName('Copiar seu endereço')
        self.numeric_code.set_copied(False)

    def paste_address(self):
        if self.peer or self.connecting:return
        self.remote_invite.setText(QApplication.clipboard().text().strip());self.remote_invite.setFocus()

    def build_home(self):
        page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(28,4,28,12);outer.setSpacing(8)
        hero=QFrame();hero.setObjectName('identityHero');hero_layout=QVBoxLayout(hero);hero_layout.setContentsMargins(0,20,0,18)
        line=QHBoxLayout();line.addStretch();label=QLabel('Este dispositivo');label.setObjectName('deviceLabel');line.addWidget(label)
        self.numeric_code=CopyAddressField();self.numeric_code.setObjectName('localAddress');self.numeric_code.copyRequested.connect(self.copy_invite)
        self.numeric_code.setFrame(False);self.numeric_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.numeric_code.setMinimumWidth(390);self.numeric_code.setMaximumWidth(490)
        self.numeric_code.setPlaceholderText('Preparando endereço…');self.numeric_code.setAccessibleName('Seu endereço Desk')
        self.show_fixed_address()
        line.addWidget(self.numeric_code)
        self.copy_address_button=QToolButton();self.copy_address_button.setIcon(QIcon(str(ASSETS/'copy.svg')))
        self.copy_address_button.setIconSize(QSize(21,21));self.copy_address_button.setToolTip('Copiar seu endereço · Ctrl+Shift+C');self.copy_address_button.setAccessibleName('Copiar seu endereço')
        self.copy_address_button.clicked.connect(self.copy_invite);line.addWidget(self.copy_address_button)
        invite=QToolButton();invite.setText('Convidar');invite.setObjectName('outlineAccent');invite.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m=QMenu(invite);m.addAction('Copiar endereço',self.copy_invite);m.addAction('Copiar convite completo',self.copy_full_invitation)
        m.addSeparator();m.addAction('Atualizar disponibilidade',self.renew_address);m.addAction('Parar recebimento',self.stop_all_sharing)
        invite.setMenu(m);line.addWidget(invite);line.addStretch();hero_layout.addLayout(line)
        self.address_caption=hint('Seu endereço fixo. A conexão só começa depois do seu aceite.')
        self.address_caption.setAlignment(Qt.AlignmentFlag.AlignCenter);hero_layout.addWidget(self.address_caption);outer.addWidget(hero)
        self.incoming_notice=QFrame();self.incoming_notice.setObjectName('incomingNotice');notice_row=QHBoxLayout(self.incoming_notice);notice_row.setContentsMargins(12,8,8,8)
        self.incoming_notice_text=QLabel();self.incoming_notice_text.setTextFormat(Qt.TextFormat.PlainText);self.incoming_notice_text.setWordWrap(True);notice_row.addWidget(self.incoming_notice_text,1)
        dismiss=QToolButton();dismiss.setText('×');dismiss.setAccessibleName('Fechar aviso de solicitação encerrada');dismiss.clicked.connect(self.incoming_notice.hide);notice_row.addWidget(dismiss)
        self.incoming_notice.hide();outer.addWidget(self.incoming_notice)
        self.incoming_notice_timer=QTimer(self);self.incoming_notice_timer.setSingleShot(True);self.incoming_notice_timer.timeout.connect(self.incoming_notice.hide)
        self.home_sections=QTabWidget();self.home_sections.setObjectName('homeSections');outer.addWidget(self.home_sections,1)
        self.device_tools=QWidget();tools=QHBoxLayout(self.device_tools);tools.setContentsMargins(0,0,0,2);tools.setSpacing(5)
        add=QToolButton();add.setText('+');add.setToolTip('Adicionar favorito');add.setAccessibleName('Adicionar favorito');add.clicked.connect(self.add_address_favorite);tools.addWidget(add)
        self.device_search=QLineEdit();self.device_search.setPlaceholderText('Buscar nos favoritos e sessões recentes')
        self.device_search.setMinimumWidth(190);self.device_search.setMaximumWidth(300)
        self.device_search.setAccessibleName('Buscar computadores salvos e recentes');self.device_search.setClearButtonEnabled(True)
        self.device_search.textChanged.connect(self.filter_devices);tools.addWidget(self.device_search,1)
        self.device_count=hint('');tools.addWidget(self.device_count);tools.addSpacing(10)
        self.view_buttons=[]
        for value in ('cards','list'):
            b=QToolButton();b.setIcon(QIcon(str(ASSETS/(value+'.svg'))));b.setIconSize(QSize(18,18));b.setCheckable(True);b.setObjectName('viewToggle')
            b.setToolTip('Exibir em '+('cartões' if value=='cards' else 'lista'))
            b.setAccessibleName(b.toolTip());b.clicked.connect(lambda checked=False,v=value:self.set_device_view(v))
            self.view_buttons.append((b,value));tools.addWidget(b)
        self.home_sections.setCornerWidget(self.device_tools,Qt.Corner.TopRightCorner)
        start=QWidget();start_layout=QVBoxLayout(start);start_layout.setContentsMargins(0,14,0,0);start_layout.setSpacing(12)
        heading=QLabel('Acesso rápido');heading.setObjectName('sectionTitle');start_layout.addWidget(heading)
        grid=TileGrid();self.quick_tiles=grid
        tiles=[('Seu Desk','Compartilhe seu endereço para receber uma solicitação de acesso.','Copiar endereço',self.copy_invite,'#bc4641'),
            ('Acesso sem supervisão','Configure os dispositivos autorizados a voltar a este computador.','Configurar acesso',lambda:self.tabs.setCurrentIndex(2),'#396ba0'),
            ('Favoritos','Guarde seus computadores e encontre seus acessos rapidamente.','Abrir favoritos',lambda:self.open_device_section(1),'#397966'),
            ('Gravar tela','Grave sua tela ou a sessão em MP4, com áudio opcional.','Abrir gravações',self.open_recordings,'#795b9e')]
        for title,description,action,handler,color in tiles:
            grid.add_tile(QuickActionCard(title,description,action,handler,color))
        start_layout.addWidget(grid)
        self.permission_panel=QFrame();self.permission_panel.setObjectName('permissionsPanel');p=QVBoxLayout(self.permission_panel)
        p.setContentsMargins(16,12,16,12);title=QLabel('Permissões para conexões recebidas');title.setObjectName('sectionTitle');p.addWidget(title)
        checks=QHBoxLayout();self.allow_control=QCheckBox('Mouse e teclado');self.allow_clipboard=QCheckBox('Área de transferência');self.allow_audio=QCheckBox('Áudio do sistema')
        for checkbox in (self.allow_control,self.allow_clipboard,self.allow_audio):checkbox.stateChanged.connect(self.update_permissions);checks.addWidget(checkbox)
        checks.addStretch();self.pause=QCheckBox('Pausar tela');self.pause.stateChanged.connect(self.pause_changed);checks.addWidget(self.pause);p.addLayout(checks)
        start_layout.addWidget(self.permission_panel)
        self.activity=hint('Preparando o endereço deste dispositivo.');start_layout.addWidget(self.activity)
        recent_heading=QHBoxLayout();label=QLabel('Sessões recentes');label.setObjectName('sectionTitle');recent_heading.addWidget(label);recent_heading.addStretch()
        show_all=action_button('Mostrar tudo →',lambda:self.open_device_section(2));show_all.setObjectName('textAction');recent_heading.addWidget(show_all)
        start_layout.addLayout(recent_heading)
        self.home_recent_preview=QListWidget();self.configure_device_list(self.home_recent_preview,'Sessões recentes · acesso rápido')
        self.home_recent_preview.setFixedHeight(174);self.home_recent_preview.itemDoubleClicked.connect(self.open_recent)
        start_layout.addWidget(self.home_recent_preview);start_layout.addStretch()
        scroll=QScrollArea();scroll.setObjectName('homeScroll');scroll.setWidgetResizable(True);scroll.setWidget(start)
        self.home_sections.addTab(scroll,'Início')
        self.home_favorites=QListWidget();self.configure_device_list(self.home_favorites,'Computadores favoritos')
        self.home_favorites.itemDoubleClicked.connect(self.open_home_favorite)
        self.home_sections.addTab(self.home_favorites,'Favoritos')
        self.recent_list=QListWidget();self.configure_device_list(self.recent_list,'Sessões recentes');self.home_sections.addTab(self.recent_list,'Sessões recentes')
        self.recent_list.itemDoubleClicked.connect(self.open_recent);self.refresh_recents()
        self.home_sections.currentChanged.connect(self.device_section_changed)
        self.set_device_view(self._desk_device_view,persist=False);self.device_section_changed(0)
        # The advanced invitation and LAN controls remain available without occupying the address-first home.
        self.address=QComboBox();self.address.setEditable(True)
        try:addresses=list(dict.fromkeys(ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith('127.')))
        except OSError:addresses=[]
        self.address.addItems(addresses or ['127.0.0.1']);self.address.hide()
        self.invite=QPlainTextEdit();self.invite.setReadOnly(True);self.invite.hide()
        self.make_invite=QPushButton('Preparar endereço');self.make_invite.clicked.connect(self.start_host);self.make_invite.hide()
        self.stop_host=QPushButton('Parar recebimento');self.stop_host.clicked.connect(self.stop_all_sharing);self.stop_host.hide()
        # Parent hidden controls so their lifetime follows the window.
        for hidden in (self.address,self.invite,self.make_invite,self.stop_host):hidden.setParent(page);hidden.hide()
        self.tabs.addTab(page,'Nova conexão')

    def build_saved(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(28,24,28,24)
        title=QLabel('Favoritos');title.setObjectName('headline');layout.addWidget(title)
        layout.addWidget(hint('Conexões são salvas automaticamente. Dispositivos autorizados reconectam sem novo aceite; os demais continuam pedindo autorização.'))
        layout.addWidget(action_button('Adicionar por endereço',self.add_address_favorite),0,Qt.AlignmentFlag.AlignLeft)
        self.saved_list=QListWidget();self.saved_list.itemDoubleClicked.connect(lambda *a:self.connect_saved());layout.addWidget(self.saved_list,1)
        row=QHBoxLayout();row.addWidget(action_button('Conectar',self.connect_saved,True));row.addWidget(action_button('Remover',self.remove_saved));row.addStretch();layout.addLayout(row)
        self.saved_name=QLineEdit();self.saved_name.setPlaceholderText('Nome do computador');layout.addWidget(self.saved_name)
        self.saved_profile=QPlainTextEdit();self.saved_profile.setMaximumHeight(70);self.saved_profile.setPlaceholderText('Cole o perfil autorizado do computador');layout.addWidget(self.saved_profile)
        self.saved_password=QLineEdit();self.saved_password.setEchoMode(QLineEdit.EchoMode.Password);self.saved_password.setPlaceholderText('Senha local opcional · mínimo de 8 caracteres');layout.addWidget(self.saved_password)
        layout.addWidget(action_button('Salvar computador',self.store_saved,True));self.saved_page=page;self.tabs.addTab(page,'Favoritos');self.refresh_saved()

    def configure_device_list(self,view,name):
        view.setObjectName('deviceCards');view.setAccessibleName(name)
        view.setResizeMode(QListView.ResizeMode.Adjust);view.setMovement(QListView.Movement.Static)
        view.setWordWrap(True);view.setIconSize(QSize(28,28));view.setSpacing(3)
        view.setItemDelegate(DeviceCardDelegate(view))
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(lambda point,v=view:self.device_context_menu(v,point))

    def set_device_view(self,mode,persist=True):
        mode='list' if mode=='list' else 'cards';self._desk_device_view=mode
        for view in (self.home_favorites,self.recent_list):
            view.setViewMode(QListView.ViewMode.ListMode if mode=='list' else QListView.ViewMode.IconMode)
            view.setWrapping(mode=='cards')
            view.setGridSize(QSize() if mode=='list' else QSize(242,153))
            for i in range(view.count()):view.item(i).setSizeHint(QSize(0,60) if mode=='list' else QSize(236,147))
            view.doItemsLayout();view.viewport().update()
        self.home_recent_preview.setViewMode(QListView.ViewMode.IconMode)
        self.home_recent_preview.setGridSize(QSize(242,153))
        for button,value in self.view_buttons:button.setChecked(value==mode)
        if persist:self.identity.configure(desk_device_view=mode)

    def device_section_changed(self,index):
        self.device_tools.setVisible(index in (1,2));self.filter_devices()

    def filter_devices(self):
        if not hasattr(self,'recent_list'):return
        query=self.device_search.text().strip().casefold()
        current=self.home_favorites if self.home_sections.currentIndex()==1 else self.recent_list
        count=0
        for view in (self.home_favorites,self.recent_list):
            for i in range(view.count()):
                item=view.item(i);visible=not query or query in item.text().casefold()
                # Ignore spacing in a numeric address, both typed and displayed.
                if not visible:visible=query.replace(' ','') in item.text().casefold().replace(' ','')
                item.setHidden(not visible)
                if view is current and visible and isinstance(item.data(Qt.ItemDataRole.UserRole),dict):count+=1
        self.device_count.setText(str(count)+' computador'+('es' if count!=1 else ''))

    def device_context_menu(self,view,point):
        item=view.itemAt(point)
        if not item or not isinstance(item.data(Qt.ItemDataRole.UserRole),dict):return
        view.setCurrentItem(item);entry=item.data(Qt.ItemDataRole.UserRole)
        menu=QMenu(view)
        if view is self.home_favorites:
            menu.addAction('Conectar',lambda:self.open_home_favorite(item))
            if entry.get('address'):menu.addAction('Copiar endereço',lambda:QApplication.clipboard().setText(format_address(entry['address'])))
            menu.addAction('Renomear…',lambda:self.rename_favorite(entry))
            colors=menu.addMenu('Cor do cartão')
            from .saved_connections import CARD_COLORS
            for label,color in zip(('Azul','Verde','Vermelho','Roxo','Dourado'),CARD_COLORS):
                action=colors.addAction(label);action.setCheckable(True);action.setChecked(entry.get('color')==color)
                action.triggered.connect(lambda checked=False,c=color:self.set_favorite_color(entry,c))
            menu.addAction('Gerenciar acesso salvo',lambda:self.tabs.setCurrentIndex(3))
            menu.addSeparator();menu.addAction('Remover dos favoritos',lambda:self.remove_favorite(entry))
        else:
            menu.addAction('Conectar novamente',lambda:self.open_recent(item))
            if entry.get('fixed'):
                try:address=format_address(normalize_address(entry['label']))
                except (KeyError,ValueError,ProtocolError):address=''
                if address:
                    menu.addAction('Copiar endereço',lambda:QApplication.clipboard().setText(address))
                    menu.addAction('Usar na barra de conexão',lambda:self.use_recent_address(address))
                    menu.addAction('Remover dos favoritos' if entry.get('favorite_id') else 'Adicionar aos favoritos',lambda:self.favorite_star_clicked(item))
        menu.exec(view.viewport().mapToGlobal(point))

    def add_address_favorite(self,checked=False,address='',name=''):
        from .saved_connections import save_address
        dialog=QDialog(self);dialog.setWindowTitle('Desk · Adicionar favorito');dialog.setMinimumWidth(430)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(24,22,24,22);layout.setSpacing(12)
        title=QLabel('Adicionar favorito');title.setObjectName('headline');layout.addWidget(title)
        layout.addWidget(hint('Guarde o número para encontrar este computador com facilidade. O acesso ainda precisa ser aprovado na outra ponta.'))
        number=QLineEdit(address);number.setPlaceholderText('Endereço Desk · 12 números');number.setAccessibleName('Endereço do favorito');number.setMaxLength(32);layout.addWidget(number)
        label=QLineEdit(name);label.setPlaceholderText('Nome do computador');label.setAccessibleName('Nome do favorito');label.setMaxLength(80);layout.addWidget(label)
        error=hint('');layout.addWidget(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);save=buttons.addButton('Salvar favorito',QDialogButtonBox.ButtonRole.AcceptRole);save.setObjectName('primary')
        def store():
            try:save_address(self.identity,label.text(),number.text(),self.view_preferences())
            except (ValueError,ProtocolError) as ex:error.setText(str(ex));return
            dialog.accept()
        save.clicked.connect(store);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.refresh_saved();self.open_device_section(1)

    def favorite_star_clicked(self,item):
        entry=item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry,dict):return
        from .saved_connections import list_connections,save_address
        id=entry.get('id') or entry.get('favorite_id')
        if id:
            favorite=next((e for e in list_connections(self.identity) if e['id']==id),None)
            if favorite:self.remove_favorite(favorite)
        elif entry.get('fixed'):
            save_address(self.identity,format_address(entry['label']),entry['label'],self.view_preferences());self.refresh_saved()

    def rename_favorite(self,entry):
        from .saved_connections import update_connection
        name,ok=QInputDialog.getText(self,'Renomear favorito','Nome do computador',text=entry['name'])
        if not ok:return
        try:update_connection(self.identity,entry['id'],name=name)
        except ValueError as ex:self.notice(str(ex));return
        self.refresh_saved()

    def set_favorite_color(self,entry,color):
        from .saved_connections import update_connection
        update_connection(self.identity,entry['id'],color=color);self.refresh_saved()

    def remove_favorite(self,entry):
        from .saved_connections import remove_connection
        if entry.get('kind')!='address':
            answer=QMessageBox.question(self,'Remover favorito?',f"Remover o acesso salvo de {entry['name']}? Para adicioná-lo novamente, será necessário obter o perfil autorizado.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        remove_connection(self.identity,entry['id']);self.refresh_saved()

    def use_recent_address(self,address):
        self.focus_remote_address();self.remote_invite.setText(address)

    def refresh_saved_views(self):
        from .saved_connections import list_connections
        self.saved_list.clear();self.home_favorites.clear()
        for entry in list_connections(self.identity):
            item=QListWidgetItem(entry['name']+('  ·  protegido por senha' if entry['locked'] else ''))
            item.setData(Qt.ItemDataRole.UserRole,entry);self.saved_list.addItem(item)
            caption=format_address(entry['address'])+'\nSolicita aprovação' if entry.get('kind')=='address' else ('Protegido por senha' if entry['locked'] else 'Acesso autorizado')
            tile=QListWidgetItem(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),entry['name']+'\n'+caption)
            tile.setData(Qt.ItemDataRole.UserRole,entry);tile.setSizeHint(QSize(235,145));self.home_favorites.addItem(tile)
            tile.setToolTip(entry['name']+'\nDuplo clique para conectar · botão direito para opções')
        if not self.home_favorites.count():
            empty=QListWidgetItem('Seus computadores favoritos\naparecerão aqui.');empty.setFlags(Qt.ItemFlag.NoItemFlags);empty.setSizeHint(QSize(280,145));self.home_favorites.addItem(empty)
        self.set_device_view(self._desk_device_view,persist=False);self.filter_devices();self.refresh_recents()

    def open_home_favorite(self,item):
        entry=item.data(Qt.ItemDataRole.UserRole)
        if not entry:return
        for i in range(self.saved_list.count()):
            if self.saved_list.item(i).data(Qt.ItemDataRole.UserRole)['id']==entry['id']:
                self.saved_list.setCurrentRow(i);self.connect_saved();return

    def refresh_recents(self):
        from .saved_connections import list_connections
        favorites=list_connections(self.identity)
        self.recent_list.clear();self.home_recent_preview.clear()
        for entry in self._desk_recent:
            if not isinstance(entry,dict):continue
            entry=dict(entry)
            favorite=next((e for e in favorites if e['id']==entry.get('saved_id') or (e.get('address') and e['address']==str(entry.get('label','')).replace(' ',''))),None)
            if favorite:entry.update(favorite_id=favorite['id'],color=favorite['color'])
            label=str(entry.get('label','Computador remoto'))
            if label.startswith(('NA1-','NAU1-')):label='Computador autorizado'
            text=(favorite['name']+'\n'+label if favorite else label)+'\nÚltima sessão · '+str(entry.get('when',''))
            item=QListWidgetItem(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),text)
            item.setData(Qt.ItemDataRole.UserRole,entry);item.setToolTip(text+'\nDuplo clique para conectar · botão direito para opções')
            self.recent_list.addItem(item)
            if self.home_recent_preview.count()<4:
                preview=QListWidgetItem(item);preview.setSizeHint(QSize(236,147));self.home_recent_preview.addItem(preview)
        if not self.recent_list.count():
            for view in (self.recent_list,self.home_recent_preview):
                item=QListWidgetItem('Nenhuma sessão recente\nSeus computadores aparecerão aqui.');item.setFlags(Qt.ItemFlag.NoItemFlags);item.setSizeHint(QSize(236,147));view.addItem(item)
        if hasattr(self,'home_favorites'):self.set_device_view(self._desk_device_view,persist=False)
        self.filter_devices()

    def open_recent(self,item):
        entry=item.data(Qt.ItemDataRole.UserRole)
        if not entry:return
        for i in range(self.saved_list.count()):
            saved=self.saved_list.item(i)
            if saved.data(Qt.ItemDataRole.UserRole)['id']==entry.get('saved_id'):
                self.saved_list.setCurrentRow(i);self.connect_saved();return
        if entry.get('fixed'):
            self.remote_invite.setText(normalize_address(entry['label']));self.connect_peer();return
        self.tabs.setCurrentIndex(0);self.home_sections.setCurrentIndex(0)
        self.remote_invite.setFocus();self.activity.setText('Para reconectar, peça o endereço atual ou use um computador favorito autorizado.')

    def build_about(self):
        from . import __version__
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(36,32,36,24)
        title=QLabel('Desk');title.setObjectName('headline');layout.addWidget(title)
        layout.addWidget(QLabel('Versão '+__version__))
        layout.addWidget(hint('Seu computador, a uma conexão de distância.'))
        layout.addSpacing(18)
        text=QLabel('Conecte pelo endereço fixo ou pelos computadores favoritos. Cada conexão recebida precisa de aceite, exceto dispositivos que você autorizou previamente para acesso sem supervisão.\n\nO endereço numérico pertence à identidade deste computador e permanece igual ao fechar, reiniciar ou desconectar. Os dados temporários da conexão são renovados internamente. Para receber acesso, mantenha o computador ligado e o Desk aberto.\n\nDesk é um aplicativo independente. Os endereços pertencem à rede Desk. Não se conecta a clientes AnyDesk.\n\nPara usar esta edição local, mantenha o ambiente instalado neste computador. A edição portátil assinada permanece separada.')
        text.setWordWrap(True);layout.addWidget(text);layout.addStretch();self.tabs.addTab(page,'Sobre o Desk')

    def prepare_address(self):
        if self.closing or not self._desk_listening_requested or self.peer or self.connecting or self.host:return
        if not self.cloud_signaling_key:
            self.set_availability('offline');self.address_caption.setText('Seu endereço fixo · configure a internet para ficar disponível')
            self.activity.setText('Falta a configuração de internet neste computador. Abra Configurações > Conexão e importe a configuração privada do proprietário.');return
        self.start_host()

    def show_fixed_address(self):
        self.numeric_code.setText(format_address(self.identity.desk_address))

    def renew_address(self):
        if self.closing or self.peer or self.connecting:return
        if self.prompts:self.address_timer.start(15000);return
        self._desk_listening_requested=True;self.start_host()

    def copy_invite(self):
        value=self.numeric_code.text().strip()
        if value:
            QApplication.clipboard().setText(value);self.activity.setText('Endereço copiado. Envie os 12 números à pessoa que fará a conexão.')
            self.copy_address_button.setIcon(QIcon(str(ASSETS/'check.svg')));self.copy_address_button.setToolTip('Endereço copiado')
            self.numeric_code.set_copied(True)
            self.copy_address_button.setAccessibleName('Endereço copiado');self._desk_copy_reset.start(2200);return
        if self.peer or self.connecting:self.activity.setText('Há uma sessão em andamento. O endereço será renovado ao encerrar.');return
        self._desk_copy_when_ready=True;self._desk_listening_requested=True;self.prepare_address()

    def copy_full_invitation(self):
        value=self.invite.toPlainText().strip()
        if value:QApplication.clipboard().setText(value);self.activity.setText('Convite completo copiado.')
        else:self.activity.setText('Prepare um endereço antes de copiar o convite completo.')

    def build_consent_window(self,prompt):
        dialog=QDialog(self);dialog.setObjectName('acceptWindow');dialog.setWindowTitle('Desk · Solicitação de conexão')
        dialog.setWindowIcon(self.windowIcon());dialog.setMinimumWidth(720)
        col=QVBoxLayout(dialog);col.setContentsMargins(0,0,0,0);col.setSpacing(0)
        header=QFrame();header.setObjectName('acceptHeader');head=QHBoxLayout(header);head.setContentsMargins(22,15,22,15)
        logo=QLabel();logo.setPixmap(self.windowIcon().pixmap(24,24));head.addWidget(logo)
        title=QLabel('Solicitação de conexão');title.setObjectName('sectionTitle');head.addWidget(title);head.addStretch();head.addWidget(hint('Desk'));col.addWidget(header)
        body=QHBoxLayout();body.setContentsMargins(22,22,22,20);body.setSpacing(24)
        identity=QFrame();identity.setObjectName('connectorCard');identity.setFixedWidth(238);left=QVBoxLayout(identity);left.setContentsMargins(20,22,20,22);left.setSpacing(12)
        avatar=QLabel();avatar.setPixmap(QIcon(str(ASSETS/'monitor.svg')).pixmap(54,54));left.addWidget(avatar)
        name=QLabel('Computador remoto');name.setObjectName('connectorName');left.addWidget(name)
        left.addWidget(hint('quer ver sua tela'))
        left.addSpacing(10);left.addWidget(hint('Origem da solicitação'))
        peer=QLabel(str(prompt.data.get('address','não informada')));peer.setTextFormat(Qt.TextFormat.PlainText);peer.setWordWrap(True)
        peer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);left.addWidget(peer)
        left.addStretch();left.addWidget(hint('Confirme com a pessoa antes de aceitar.'));body.addWidget(identity)
        right=QVBoxLayout();right.setSpacing(12)
        heading=QLabel('Permissões da conexão');heading.setObjectName('connectorName');right.addWidget(heading)
        right.addWidget(hint('Escolha o que o computador remoto poderá fazer.'))
        profile=QComboBox();profile.setAccessibleName('Perfil de permissões');profile.addItems(['Permissões atuais','Somente visualizar','Personalizado']);right.addWidget(profile)
        checks=[];initial=[]
        details=['Mover o cursor e digitar neste computador.','Enviar e receber texto copiado.','Ouvir o som transmitido deste computador.']
        for (source,label),description in zip([(self.allow_control,'Mouse e teclado'),(self.allow_clipboard,'Área de transferência'),(self.allow_audio,'Áudio do sistema')],details):
            box=QCheckBox(label);box.setChecked(source.isChecked());right.addWidget(box);right.addWidget(hint(description));checks.append((source,box));initial.append(source.isChecked())
        def select_profile(index):
            if index==2:return
            for i,(_,box) in enumerate(checks):
                box.blockSignals(True);box.setChecked(initial[i] if index==0 else False);box.blockSignals(False)
        profile.currentIndexChanged.connect(select_profile)
        for _,box in checks:box.toggled.connect(lambda checked:profile.setCurrentIndex(2))
        remember=QCheckBox('Permitir reconexões deste computador sem novo aceite')
        remember.setObjectName('rememberDevice');remember.setEnabled(bool(prompt.data.get('device_public')));remember.setChecked(bool(prompt.data.get('device_public')))
        remember.setToolTip('Ao aceitar, este dispositivo será autorizado por sua chave. Você pode revogar em Configurações > Conexão. O Desk precisa permanecer aberto.')
        right.addWidget(remember);right.addWidget(hint('A conexão será salva na outra ponta. Revogue o acesso quando quiser.'))
        dialog.remember_device=remember
        right.addStretch();body.addLayout(right,1);col.addLayout(body)
        footer=QFrame();footer.setObjectName('acceptFooter');bottom=QHBoxLayout(footer);bottom.setContentsMargins(22,14,22,14)
        bottom.addWidget(hint('A tela só será compartilhada depois do seu aceite.'),1)
        buttons=QDialogButtonBox();reject=buttons.addButton('Recusar',QDialogButtonBox.ButtonRole.RejectRole);reject.setObjectName('dangerOutline')
        accept=buttons.addButton('Aceitar',QDialogButtonBox.ButtonRole.AcceptRole);accept.setObjectName('acceptConnection');accept.setAutoDefault(False);accept.setDefault(False)
        reject.setDefault(True);reject.setFocus();buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);bottom.addWidget(buttons);col.addWidget(footer)
        return dialog,checks

    def consent_dialog(self,prompt):
        if prompt.is_cancelled() or self.closing:return False
        self._remember_approved_public=None
        self.incoming_notice.hide()
        dialog,checks=self.build_consent_window(prompt)
        self.notifications.prepare_dialog(dialog)
        timer=QTimer(dialog);timer.setInterval(75);timer.timeout.connect(lambda:dialog.reject() if prompt.is_cancelled() or self.closing else None);timer.start()
        allowed=dialog.exec()==QDialog.DialogCode.Accepted and not prompt.is_cancelled() and not self.closing
        if allowed:
            for source,box in checks:source.setChecked(box.isChecked())
            if self.host:self.host.permissions=self.permissions()
            if dialog.remember_device.isEnabled() and dialog.remember_device.isChecked():self._remember_approved_public=prompt.data.get('device_public')
        dialog.deleteLater()
        return allowed

    def on_event(self,name,data):
        if isinstance(data,dict) and data.get('_ui_epoch',self.connection_epoch)!=self.connection_epoch:return
        if name=='incoming_lookup':
            if self.numeric_invite and data.get('id')==self.numeric_invite.id and not self.peer:
                self.notifications.notify('connection','Solicitação de conexão',data['text'],True,'connection')
            return
        if name=='file_received':self.notifications.notify('file_received','Arquivo recebido',data.get('name','Arquivo recebido e conferido.'),destination='files')
        if name in ('connect_stage','connect_error') and data.get('epoch',self.connection_epoch)!=self.connection_epoch:return
        if name.startswith('numeric_') and (not self.numeric_invite or data.get('id')!=self.numeric_invite.id):return
        self._core_event(name,data)
        if self.closing:return
        self.update_session_actions()
        if name=='numeric_ready' and self.numeric_invite and data.get('id')==self.numeric_invite.id:
            self._desk_address_online=True
            self.set_availability('online')
            self.address_caption.setText('Endereço fixo deste dispositivo · aprovação necessária')
            self.activity.setText('Disponível. Compartilhe seu endereço para receber uma solicitação.');self.status.setText('Disponível')
            self.address_timer.start(max(1000,int((data.get('expires',time.time()+600)-time.time()-30)*1000)))
            if self._desk_copy_when_ready:self._desk_copy_when_ready=False;self.copy_invite()
        elif name=='connected':
            self.set_availability('active')
            self.show_fixed_address();self.address_timer.stop();self.address_caption.setText('Sessão ativa · seu endereço permanece o mesmo')
            self.session_nav.setText('Sessão ativa');self.session_nav.setIcon(QIcon(str(ASSETS/'monitor.svg')))
            if self.peer and self.peer.role=='viewer':
                label=self._desk_last_remote or 'Computador remoto';label='Computador autorizado' if label.startswith(('NA1-','NAU1-')) else label
                from .connection_catalog import remember_recent
                self._desk_recent=remember_recent(self.identity,dict(label=label,when=time.strftime('%d/%m %H:%M'),saved_id=self.active_saved_id,fixed=bool(getattr(self.peer,'address_lookup',None))))
                self.refresh_recents()
        elif name in ('host_expired','numeric_expired','disconnected'):
            self.show_fixed_address();self._desk_address_online=False
            self.set_availability('preparing' if self._desk_listening_requested else 'offline')
            self.address_timer.stop()
            self.session_nav.setText('Sessão');self.session_nav.setIcon(QIcon())
            if self._desk_listening_requested and not self.peer and not self.connecting:
                self.stop_sharing();QTimer.singleShot(300,self.prepare_address)
        elif name=='numeric_error':
            self.show_fixed_address();self._desk_address_online=False
            self.set_availability('preparing' if self._desk_listening_requested else 'offline')
            self.address_caption.setText('Seu endereço fixo · reconectando ao serviço de internet')
            if self._desk_listening_requested and not self.peer and not self.connecting:self.address_timer.start(max(5000,min(300000,data.get('retry_ms',15000))))
        elif name in ('host_error','persistent_error'):
            if not self._desk_address_online and not self.peer:self.set_availability('offline')
        elif name in ('stats','receive_stats'):
            if name=='stats':self._last_stream_stats=data
            stats=getattr(self,'_last_stream_stats',{})
            received=getattr(self.peer,'receive_metrics',{}) if self.peer else {}
            fps=received.get('received_fps',stats.get('effective_fps',stats.get('frames',0)/max(.001,stats.get('seconds',1))))
            if stats:
                self.metrics.setToolTip(self.metrics.text());self.metrics.setText(f"{stats.get('width',0)} × {stats.get('height',0)}  ·  {fps:.0f} FPS recebidos  ·  {stats.get('rtt_ms',0):.0f} ms")
            self.record_connection_metrics(stats,received)
        self.on_connection_event(name,data)
        self.on_collaboration_event(name,data)
        self.on_advanced_event(name,data)
        if name=='incoming_cancelled':
            self.notifications.dismiss_request('consent')
            text=data['text'];self.incoming_notice_text.setText(text);self.incoming_notice.show();self.incoming_notice_timer.start(6500)
            self.activity.setText(text);self.statusBar().showMessage(text,6500)

    def record_connection_metrics(self,stats,received):
        path=os.environ.get('DESK_METRICS_PATH')
        if not path or time.monotonic()-getattr(self,'_last_metrics_write',0)<.9:return
        self._last_metrics_write=time.monotonic()
        try:
            import json
            from pathlib import Path
            target=Path(path)
            if target.exists() and target.stat().st_size>2*1024*1024:return
            values={k:v for source in (stats,received) for k,v in source.items() if k in ('width','height','encode_ms','rtt_ms','delivery_ms','effective_fps','received_fps','decode_ms','received_kbps','deflate','vp8') and type(v) in (int,float)}
            outer=getattr(getattr(getattr(self.peer,'channel',None),'sock',None),'outer',None)
            pairs=getattr(outer,'candidate_types',[])
            values.update(time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),candidate_types=[[a,b] for a,b in pairs if a in ('host','srflx','prflx','relay') and b in ('host','srflx','prflx','relay')],force_relay=bool(getattr(outer,'relay_only',False)))
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('a',encoding='utf-8') as output:output.write(json.dumps(values)+'\n')
        except (OSError,TypeError,ValueError):pass

    def style_native_titlebar(self):
        if os.name!='nt' or os.environ.get('QT_QPA_PLATFORM')=='offscreen':return
        try:
            import ctypes
            hwnd=int(self.winId());dwm=ctypes.windll.dwmapi.DwmSetWindowAttribute
            for attribute,value in [(20,1),(35,0x202020),(36,0xF0F0F0)]:
                data=ctypes.c_int(value);dwm(ctypes.c_void_p(hwnd),attribute,ctypes.byref(data),ctypes.sizeof(data))
        except (AttributeError,OSError):pass

STYLE="""
QWidget {font-family:'Segoe UI';font-size:13px;color:#eceeef;background:#232121;}
QMainWindow {background:#232121;} QFrame#titleStrip{background:#282a2d;border-bottom:1px solid #36393d;}
QFrame#addressBar{background:#191b1d;border-bottom:1px solid #3c3e42;}
QLabel#brand{font-size:17px;font-weight:600;background:transparent;}
QLabel#status{font-size:12px;color:#a7c9ad;background:transparent;padding:3px 8px;}
QLabel#onlineDot{color:#68c56e;background:transparent;} QLabel#headline{font-size:25px;font-weight:600;}
QLabel#muted{color:#aeb2b8;background:transparent;} QLabel#deviceLabel{font-size:16px;color:#bdc1c6;}
QLabel#sectionTitle{font-weight:600;} QLabel#tileTitle{font-size:16px;font-weight:600;background:transparent;}
QLabel#tileDescription{color:#b8bdc4;background:transparent;}
QFrame#identityHero{border:0;} QFrame#featureTile{background:#282b2e;border:1px solid #3b3f44;border-radius:6px;}
QFrame#featureTile:hover{border-color:#5b6168;}
QFrame#permissionsPanel{background:#25282b;border:1px solid #3b3f44;border-radius:6px;}
QFrame#permissionsPanel QLabel,QFrame#permissionsPanel QCheckBox{background:transparent;}
QPushButton{background:#303439;border:1px solid #51565d;border-radius:5px;padding:8px 16px;min-height:18px;}
QPushButton:hover{background:#3a3f45;border-color:#707780;}
QPushButton:pressed{background:#24282c;border-color:#e17972;}
QPushButton:focus{border-color:#e8918b;}
QPushButton:disabled{color:#81868d;border-color:#3b3e43;background:#292c30;}
QPushButton#primary{background:#e34d44;border-color:#e34d44;color:white;font-weight:600;}
QPushButton#primary:hover{background:#ef5c52;border-color:#ef5c52;}
QPushButton#primary:pressed{background:#bf3933;border-color:#ffaba4;}
QPushButton#primary:focus{border-color:#ffd5d1;}
QPushButton#primary:disabled{background:#693b39;border-color:#693b39;color:#c09a97;}
QPushButton#navTab{background:transparent;border:1px solid transparent;min-width:108px;padding:5px 12px;}
QPushButton#navTab:hover{background:#34383d;}
QPushButton#navTab[selected="true"]{background:#34383d;color:#fff;}
QPushButton#navTab:focus{border-color:#e8918b;}
QFrame#navigationIndicator{background:#ef655b;border:0;}
QPushButton#tileAction{background:#303439;border:1px solid #51565d;font-weight:600;text-align:center;padding:5px 10px;}
QPushButton#tileAction:hover{background:#3a3f45;border-color:#707780;color:white;}
QPushButton#tileAction:pressed{background:#24282c;border-color:#e17972;}
QPushButton#tileAction:focus{border-color:#e8918b;}
QToolButton{background:transparent;border:1px solid transparent;border-radius:5px;padding:6px;color:#dde0e4;font-size:18px;}
QToolButton:hover{background:#373c42;}
QToolButton:pressed{background:#24282c;border-color:#e17972;}
QToolButton:focus{border-color:#e8918b;}
QToolButton:disabled{color:#777d85;background:transparent;border-color:transparent;}
QToolButton#outlineAccent{border:1px solid #7e5652;color:#f59a92;font-size:13px;padding:5px 11px;}
QToolButton#outlineAccent:hover{background:#423230;border-color:#ba6f68;}
QToolButton#outlineAccent:pressed{background:#532f2b;}
QToolButton#outlineAccent:focus{border-color:#ffd5d1;}
QToolButton#viewToggle{font-size:17px;padding:4px 8px;color:#929aa0;border:1px solid transparent;}
QToolButton#viewToggle:checked{background:#393333;border-color:#8e524c;color:#f0786f;}
QPushButton#textAction{background:transparent;border:0;padding:2px 4px;color:#bfbfbf;}
QPushButton#textAction:hover{color:#f0786f;}
QToolButton::menu-indicator{image:none;}
QLineEdit,QPlainTextEdit,QComboBox{background:#191b1e;border:1px solid #51565d;border-radius:5px;padding:8px;selection-background-color:#91423f;}
QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus{border-color:#cf6862;}
QLineEdit#remoteAddress{background:#151719;border-color:#3d4248;font-size:15px;padding:6px 12px;}
QLineEdit#remoteAddress:focus{border-color:#e8918b;}
QLineEdit#localAddress{background:transparent;color:#f04a43;font-size:38px;font-weight:600;letter-spacing:1px;border:0;padding:4px 8px;}
QComboBox{min-height:20px;} QCheckBox{spacing:8px;padding:4px 0;} QCheckBox::indicator{width:16px;height:16px;}
QCheckBox::indicator:unchecked{background:#181818;border:1px solid #777;border-radius:2px;}
QCheckBox::indicator:checked{background:#ef443b;border:1px solid #ef443b;border-radius:2px;}
QTabWidget#workspace::pane{border:0;} QTabWidget#homeSections::pane{border:0;border-top:1px solid #444;}
QTabBar::tab{background:transparent;color:#9d9d9d;padding:12px 20px;border-bottom:2px solid transparent;}
QTabBar::tab:selected{color:#f15a52;border-bottom:2px solid #ef443b;font-weight:600;} QTabBar::tab:hover{color:#eee;}
QListWidget{background:#202224;border:1px solid #41464d;border-radius:5px;padding:10px;outline:0;}
QListWidget#deviceCards{border:0;padding:4px 0;} QListWidget#deviceCards::item{background:#292d31;border:1px solid #515860;border-radius:5px;padding:10px;}
QListWidget#deviceCards::item:selected{background:#453938;border-color:#e86d64;}
QListWidget::item{padding:12px;} QListWidget::item:selected{background:#493331;color:#fff;}
QMenu{background:#292d31;border:1px solid #555c65;padding:5px;border-radius:5px;} QMenu::item{padding:8px 26px;border-radius:3px;} QMenu::item:selected{background:#493632;}
QMenu::item:disabled{color:#7b8189;} QMenu::separator{height:1px;background:#43484f;margin:5px 8px;}
QToolTip{background:#343a41;color:#f1f2f4;border:1px solid #626b76;padding:5px;}
QScrollArea{border:0;} QStatusBar{color:#999;border-top:1px solid #363636;font-size:12px;}
QScrollBar:vertical{background:#242424;width:10px;margin:0;} QScrollBar::handle:vertical{background:#505050;min-height:32px;border-radius:4px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QSplitter::handle{background:#444;width:3px;} QDialog{background:#252525;}
QFrame#sessionToolbar{background:#272727;border:1px solid #3c3c3c;border-radius:3px;}
QFrame#sessionToolbar QCheckBox{background:transparent;}
QFrame#acceptHeader{background:#2b2b2b;border-bottom:1px solid #474747;}
QFrame#incomingNotice{background:#303a42;border:1px solid #526372;border-radius:3px;}
QFrame#incomingNotice QLabel{background:transparent;color:#d5e0e8;}
QFrame#acceptHeader QLabel{background:transparent;}
QFrame#connectorCard{background:#29343e;border:1px solid #4b5964;border-radius:4px;}
QFrame#connectorCard QLabel{background:transparent;}
QLabel#connectorName{font-size:18px;font-weight:600;background:transparent;}
QFrame#acceptFooter{background:#272727;border-top:1px solid #414141;}
QFrame#acceptFooter QLabel{background:transparent;}
QPushButton#acceptConnection{background:#357b56;border-color:#4f9c70;color:white;font-weight:600;min-width:82px;}
QPushButton#acceptConnection:hover{background:#439264;}
QPushButton#acceptConnection:pressed{background:#285e41;border-color:#b3e4c7;}
QPushButton#acceptConnection:focus{border-color:#b3e4c7;}
QToolButton#sessionTool{font-size:13px;padding:7px 10px;}
QPushButton#dangerOutline{border-color:#a85d56;color:#f08077;background:#302624;}
QPushButton#dangerOutline:hover{background:#563632;}
QPushButton#dangerOutline:pressed{background:#6c3831;border-color:#ffaba4;}
QPushButton#dangerOutline:focus{border-color:#ffaba4;}
QPushButton#dangerOutline:disabled{border-color:#49403f;color:#81716f;}
QPushButton:checked{background:#493a38;border-color:#a96a64;}
QTabWidget#sessionSide::pane{border:1px solid #404040;}
QTabWidget#sessionSide QTabBar::tab{padding:9px 12px;}
QListWidget#settingsNavigation{background:#262626;border:0;border-right:1px solid #414141;padding:14px 6px;}
QListWidget#settingsNavigation::item{padding:12px 10px;border-left:2px solid transparent;}
QListWidget#settingsNavigation::item:selected{background:#3c302e;border-left-color:#ee635a;}
"""
STYLE+='\nQCheckBox::indicator:checked {image:url("'+(ASSETS/'check.svg').as_posix()+'");}\n'
STYLE+=CONNECTION_STYLE
STYLE+=IMAGE_STYLE
from .desk_theme import STYLE as FIDELITY_STYLE
STYLE+=FIDELITY_STYLE
