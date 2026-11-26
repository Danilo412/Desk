"""Image profiles and fullscreen preferences mapped to existing video limits."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QRadioButton,QPushButton,QButtonGroup,QComboBox,QCheckBox,QToolButton,QScrollArea,QFrame

PRESETS=(('quality','Melhor qualidade','Até 1440p · 30 FPS · mais detalhes',(2560,30)),
         ('balanced','Equilibrado','Até 1080p · 30 FPS · uso geral',(1920,30)),
         ('performance','Melhor desempenho','Até 720p · 30 FPS · menos tráfego',(1280,30)),
         ('remote','Rede distante','Até 960p · 24 FPS · mais fluidez em outra rede ou 4G',(960,24)))

class ImageSettingsPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        col=QVBoxLayout(self);col.setContentsMargins(16,14,16,14);col.setSpacing(8)
        title=QLabel('Imagem e qualidade');title.setObjectName('connectorName');col.addWidget(title)
        section=QLabel('Qualidade');section.setObjectName('imageSection');col.addWidget(section)
        self.group=QButtonGroup(self);self.buttons={}
        choices=QWidget();choices.setObjectName('segmentedGroup');segments=QHBoxLayout(choices);segments.setContentsMargins(0,0,0,0);segments.setSpacing(0)
        for key,label,description,value in PRESETS:
            button=QPushButton({'quality':'Qualidade','balanced':'Equilibrado','performance':'Desempenho','remote':'Distante'}[key]);button.setCheckable(True);button.setObjectName('segment')
            button.setAccessibleName(label);button.setToolTip(label+' · '+description)
            self.group.addButton(button);self.buttons[key]=button;segments.addWidget(button,1)
            button.toggled.connect(lambda checked,v=value:owner.choose_image_profile(v) if checked else None)
        col.addWidget(choices)
        self.profile_description=QLabel();self.profile_description.setObjectName('imageHint');self.profile_description.setWordWrap(True);col.addWidget(self.profile_description)
        self.custom=QRadioButton('Personalizado');self.group.addButton(self.custom);col.addWidget(self.custom)
        label=QLabel('Modo de exibição');label.setObjectName('imageSection');col.addWidget(label)
        self.display=QComboBox(self)
        for i in range(owner.display.count()):self.display.addItem(owner.display.itemText(i),owner.display.itemData(i))
        self.display.setAccessibleName('Modo de exibição da tela remota');self.display.hide()
        self.display.currentIndexChanged.connect(lambda index:owner.display.setCurrentIndex(owner.display.findData(self.display.currentData())))
        modes=QWidget();modes.setObjectName('segmentedGroup');mode_row=QHBoxLayout(modes);mode_row.setContentsMargins(0,0,0,0);mode_row.setSpacing(0)
        self.view_group=QButtonGroup(self);self.view_buttons={}
        for key,label in [('original','Original'),('fit','Ajustar'),('stretch','Esticar')]:
            button=QPushButton(label);button.setCheckable(True);button.setObjectName('segment');button.setAccessibleName('Exibição: '+label)
            button.clicked.connect(lambda checked=False,k=key:owner.display.setCurrentIndex(owner.display.findData(k)))
            self.view_group.addButton(button);self.view_buttons[key]=button;mode_row.addWidget(button,1)
        col.addWidget(modes);col.addSpacing(5)
        self.start_fullscreen=QCheckBox('Iniciar próximas sessões em tela cheia');self.start_fullscreen.toggled.connect(owner.start_fullscreen.setChecked);col.addWidget(self.start_fullscreen)
        self.pin=QCheckBox('Manter a barra de tela cheia visível');self.pin.toggled.connect(owner.set_fullscreen_pin);col.addWidget(self.pin)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('imageHint');col.addWidget(self.summary)
        self.advanced_toggle=QToolButton();self.advanced_toggle.setText('Mais opções');self.advanced_toggle.setObjectName('sessionTool');self.advanced_toggle.setCheckable(True);self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);col.addWidget(self.advanced_toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.advanced=QWidget();advanced=QVBoxLayout(self.advanced);advanced.setContentsMargins(0,0,0,0);advanced.setSpacing(8)
        advanced.addWidget(QLabel('Resolução e fluidez'))
        self.quality=QComboBox()
        for i in range(owner.quality.count()):self.quality.addItem(owner.quality.itemText(i),owner.quality.itemData(i))
        advanced.addWidget(self.quality);self.quality.currentIndexChanged.connect(lambda index:owner.choose_image_profile(self.quality.currentData()))
        advanced.addWidget(QLabel('Codificação'))
        self.codec=QComboBox()
        for i in range(owner.codec.count()):self.codec.addItem(owner.codec.itemText(i),owner.codec.itemData(i))
        self.codec.currentIndexChanged.connect(lambda index:owner.codec.setCurrentIndex(owner.codec.findData(self.codec.currentData())));advanced.addWidget(self.codec)
        note=QLabel('O Desk otimiza automaticamente a taxa de bits e o ritmo dos quadros para conexões locais ou distantes, preservando a nitidez do texto. Original mostra um pixel por pixel; Ajustar mantém as proporções dentro da janela.');note.setWordWrap(True);note.setObjectName('imageHint');advanced.addWidget(note)
        self.advanced.hide();col.addWidget(self.advanced)
        from .ui_motion import reveal_widget
        self.advanced_toggle.toggled.connect(lambda on:reveal_widget(self.advanced,on,owner));self.advanced_toggle.toggled.connect(lambda on:self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow))
        self.custom.toggled.connect(lambda checked:self.advanced_toggle.setChecked(True) if checked else None)
        owner._image_panels.append(self);self.sync()

    def sync(self):
        owner=self.owner;current=tuple(owner.quality.currentData() or (1920,30))
        matched=next((key for key,label,description,value in PRESETS if value==current),None)
        widgets=[*self.buttons.values(),*self.view_buttons.values(),self.custom,self.display,self.quality,self.codec,self.start_fullscreen,self.pin]
        previous=[widget.blockSignals(True) for widget in widgets]
        try:
            (self.buttons[matched] if matched else self.custom).setChecked(True)
            self.display.setCurrentIndex(max(0,self.display.findData(owner.display.currentData())))
            self.view_buttons[owner.display.currentData()].setChecked(True)
            self.profile_description.setText(next((description for key,label,description,value in PRESETS if key==matched),'Resolução e fluidez personalizadas.'))
            self.quality.setCurrentIndex(owner.quality.currentIndex());self.codec.setCurrentIndex(max(0,self.codec.findData(owner.codec.currentData())))
            self.start_fullscreen.setChecked(owner.start_fullscreen.isChecked())
            pinned=owner.fullscreen_tools.pin.isChecked() if hasattr(owner,'fullscreen_tools') else owner.identity.settings().get('desk_fullscreen_bar_pinned',False)
            self.pin.setChecked(pinned)
            self.summary.setText('Solicitado: '+owner.quality.currentText()+'\n'+owner.display.currentText())
        finally:
            for widget,blocked in zip(widgets,previous):widget.blockSignals(blocked)

class ImageControls:
    def make_image_panel(self,compact=False):
        panel=ImageSettingsPanel(self)
        if not compact:return panel
        scroll=QScrollArea();scroll.setObjectName('imagePopup');scroll.setWidgetResizable(True);scroll.setWidget(panel);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setFixedSize(450,560)
        return scroll

    def choose_image_profile(self,value):
        if value is None:return
        index=next((i for i in range(self.quality.count()) if tuple(self.quality.itemData(i))==tuple(value)),None)
        if index is not None:self.quality.setCurrentIndex(index)

    def sync_image_panels(self):
        for panel in self._image_panels:panel.sync()

    def set_fullscreen_pin(self,value):
        if hasattr(self,'fullscreen_tools'):self.fullscreen_tools.pin.setChecked(value)
        else:self.identity.configure(desk_fullscreen_bar_pinned=bool(value))
        self.sync_image_panels()

    def begin_preferred_fullscreen(self,epoch):
        if self.closing or epoch!=self.connection_epoch or not self.peer or self.peer.role!='viewer' or self._fullscreen:return
        if self.start_fullscreen.isChecked():self.fullscreen()

    def minimize_remote_session(self):
        self.exit_fullscreen();self.showMinimized()
