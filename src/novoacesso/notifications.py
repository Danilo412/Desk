"""Desk-owned notifications and foreground prompts; no automatic consent."""
from PySide6.QtCore import QObject,QTimer,Qt,Signal
from PySide6.QtWidgets import QApplication,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton

class NotificationToast(QFrame):
    activated=Signal()
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        self.setWindowTitle('Desk · notificação')
        self.setObjectName('deskNotification');self.setFixedWidth(360)
        col=QVBoxLayout(self);col.setContentsMargins(16,12,12,12);col.setSpacing(8)
        row=QHBoxLayout();self.title=QLabel();self.title.setTextFormat(Qt.TextFormat.PlainText);self.title.setObjectName('sectionTitle');self.title.setWordWrap(True);row.addWidget(self.title,1)
        close=QPushButton('×');close.setAccessibleName('Fechar notificação');close.setFixedWidth(30);close.clicked.connect(self.hide);row.addWidget(close);col.addLayout(row)
        self.body=QLabel();self.body.setTextFormat(Qt.TextFormat.PlainText);self.body.setWordWrap(True);col.addWidget(self.body)
        self.open=QPushButton('Abrir no Desk');self.open.clicked.connect(self.activated);col.addWidget(self.open,0,Qt.AlignmentFlag.AlignRight)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.hide)
    def present(self,title,body,screen):
        self.title.setText(title);self.body.setText(str(body)[:240]);self.adjustSize()
        area=screen.availableGeometry();self.move(area.right()-self.width()-18,area.top()+58)
        self.show();self.raise_();self.timer.start(9000)

class NotificationCenter(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.toast=None;self.destination='chat';self.last_kind=''
        QApplication.instance().aboutToQuit.connect(self.stop)
    def bring_forward(self):
        target=self.window.fullscreen_window or self.window
        if target.isMinimized():target.showNormal()
        else:target.show()
        target.raise_();target.activateWindow();QApplication.alert(target,0)
    def prepare_dialog(self,dialog):
        if not self.window.identity.settings().get('foreground_requests',True):return
        self.bring_forward();dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        def focus():
            try:
                if dialog.isVisible():dialog.raise_();dialog.activateWindow()
            except RuntimeError:pass
        QTimer.singleShot(0,dialog,focus)
    def notify(self,kind,title,text,urgent=False,destination='chat'):
        if self.window.closing:return
        repeated=bool(self.toast and self.toast.isVisible() and self.last_kind==kind)
        self.last_kind=kind;self.destination=destination
        if urgent and not repeated and self.window.identity.settings().get('foreground_requests',True):self.bring_forward()
        settings=self.window.identity.settings()
        if not settings.get('notifications_enabled',True):return
        if kind=='chat' and not settings.get('notification_previews',True):text='Você recebeu uma nova mensagem na sessão.'
        if self.toast is None:
            self.toast=NotificationToast();self.toast.activated.connect(self.open_destination)
        screen=self.window.screen() or QApplication.primaryScreen()
        if screen:self.toast.present(title,text,screen)
    def dismiss_request(self,kind):
        expected={'consent':'connection','save_file':'file_offer','advanced_action':'request'}.get(kind)
        if self.toast and expected==self.last_kind:self.toast.hide()
    def open_destination(self):
        self.bring_forward()
        if self.destination=='updates':self.window.open_update_settings();self.window.updates.show_offer()
        if self.destination in ('chat','files') and self.window.peer:self.window.open_session_panel(0 if self.destination=='chat' else 1)
        if self.toast:self.toast.hide()
    def incoming(self,kind,data):
        if kind=='consent':self.notify('connection','Solicitação de conexão','Uma pessoa está aguardando seu aceite no Desk.',True,'connection')
        elif kind=='save_file':self.notify('file_offer','Arquivo para receber',str(data.get('name','Arquivo'))+' · escolha onde salvar.',True,'files')
        elif kind=='advanced_action':self.notify('request','Solicitação da sessão','A outra ponta aguarda sua confirmação.',True,'connection')
    def test_message(self):self.notify('chat','Desk · notificação de teste','As próximas mensagens aparecerão aqui, mesmo com outro aplicativo à frente.')
    def test_request(self):
        from PySide6.QtWidgets import QDialog,QDialogButtonBox
        self.notify('test','Desk · teste de solicitação','Esta é uma prévia. Nenhuma conexão será aceita ou iniciada.',True,'connection')
        dialog=QDialog(self.window);dialog.setWindowTitle('Desk · teste de solicitação');col=QVBoxLayout(dialog)
        text=QLabel('Este aviso veio para a frente. Nenhum acesso ou transferência foi autorizado.');text.setWordWrap(True);col.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);col.addWidget(buttons)
        self.prepare_dialog(dialog);dialog.exec();dialog.deleteLater()
    def stop(self):
        if self.toast:self.toast.timer.stop();self.toast.close();self.toast.deleteLater();self.toast=None
