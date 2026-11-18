"""Session menus and read-only connection information."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu,QDialog,QLabel,QVBoxLayout,QGridLayout,QPushButton


class SessionTools:
    def make_monitor_menu(self,parent):
        menu=QMenu(parent)
        menu.aboutToShow.connect(lambda:self.populate_monitor_menu(menu))
        return menu

    def populate_monitor_menu(self,menu):
        menu.clear()
        previous=getattr(menu,'_selection_group',None)
        if previous:previous.deleteLater()
        menu._selection_group=QActionGroup(menu);menu._selection_group.setExclusive(True)
        live=bool(self.peer and getattr(self.peer,'role','')=='viewer')
        if not live or not self.monitor.count():
            menu.addAction('Nenhum monitor remoto disponível').setEnabled(False);return
        menu.addSection('Telas do computador remoto')
        for i in range(self.monitor.count()):
            label=self.monitor.itemText(i)
            action=menu.addAction(label);action.setCheckable(True);action.setChecked(i==self.monitor.currentIndex())
            action.setData(self.monitor.itemData(i));menu._selection_group.addAction(action)
            action.triggered.connect(lambda checked=False,index=i:self.monitor.setCurrentIndex(index))

    def refresh_monitor_tools(self):
        if not hasattr(self,'monitor_picker'):return
        label=self.monitor.currentText() or 'Monitores'
        if self.monitor.currentData()==0:label='Todas as telas'
        live=bool(self.peer and getattr(self.peer,'role','')=='viewer')
        self.monitor_picker.setText(label);self.monitor_picker.setEnabled(live)
        if hasattr(self,'fullscreen_tools'):
            self.fullscreen_tools.monitors.setText(label);self.fullscreen_tools.monitors.setEnabled(live)
            self.fullscreen_tools.image.setEnabled(live)
            self.fullscreen_tools.details.setEnabled(bool(self.peer))

    def session_information(self):
        peer=self.peer
        closed=getattr(peer,'closed',None)
        live=bool(peer and not (closed and closed.is_set()))
        result={'Computador':self.connection_display_name() if live else '—',
                'Estado':self.session_badge.text() if live else 'Sem sessão ativa',
                'Duração':self.session_elapsed.text() or '—','Conexão':'—','Proteção':'—',
                'Tela recebida':'—','Exibição':self.display.currentText(),'Qualidade solicitada':self.quality.currentText(),
                'Mouse e teclado':'Não permitido','Texto copiado':'Não permitido','Áudio':'Não permitido',
                'Rota ICE':'—','Fluxo recebido':'—','Captura e codificação':'—','Etapas da captura':'—','Entrega do quadro':'—','Controle remoto':'—'}
        if not live:return result
        stats=getattr(self,'_last_stream_stats',{})
        def metric(key):
            value=stats.get(key)
            return f'{value:.1f}' if type(value) in (int,float) and 0<=value<1e8 else '—'
        result['Captura e codificação']=f"{stats.get('capture','—') if stats.get('capture') in ('MSS','DXGI','Serviço Windows') else '—'} · captura {metric('capture_ms')} ms · codificação {metric('encode_ms')} ms"
        result['Etapas da captura']=f"Consulta {metric('capture_probe_ms')} ms · obtenção {metric('capture_grab_ms')} ms · escala {metric('capture_scale_ms')} ms"
        result['Entrega do quadro']=f"{metric('delivery_ms')} ms · fila {metric('pending_frames')} quadros / {metric('pending_kib')} KiB"
        result['Controle remoto']=('Canal dedicado' if getattr(getattr(peer,'fast_input',None),'active',False) or stats.get('input_fast')==1 else 'Canal principal')+f" · aplicação {metric('input_apply_ms')} ms"
        permissions=getattr(peer,'permissions',{})
        for key,title in [('control','Mouse e teclado'),('clipboard','Texto copiado'),('audio','Áudio')]:
            result[title]='Permitido' if permissions.get(key) is True else 'Não permitido'
        channel=getattr(peer,'channel',None);sock=getattr(channel,'sock',None)
        if sock is not None:
            try:result['Proteção']=sock.version() or 'Não informado'
            except (AttributeError,OSError):result['Proteção']='Não informado'
            outer=getattr(sock,'outer',None)
            result['Conexão']=str(getattr(outer,'route_info','Rota não informada'))[:160] if outer is not None else 'Conexão direta'
            pairs=getattr(outer,'candidate_types',[]) if outer is not None else []
            if pairs and all(a in ('host','srflx','prflx','relay') and b in ('host','srflx','prflx','relay') for a,b in pairs):result['Rota ICE']=' / '.join(a+' → '+b for a,b in pairs)
            received=getattr(peer,'receive_metrics',{})
            if received:result['Fluxo recebido']=f"{received.get('received_fps',0):.1f} FPS · {received.get('received_kbps',0)/1000:.2f} Mbit/s · decodificação {received.get('decode_ms',0):.1f} ms"
        if getattr(peer,'role','')=='viewer':
            result['Estado']='Controle ativo' if self.canvas.allow_control else 'Somente visualização'
            if self.canvas.image is not None:result['Tela recebida']=f'{self.canvas.image.width()} × {self.canvas.image.height()}'
        else:
            result['Estado']='Compartilhando a tela';result['Exibição']='Configurada pela outra ponta';result['Tela recebida']='Não se aplica'
            width,fps=getattr(peer,'width',None),getattr(peer,'fps',None)
            result['Qualidade solicitada']=f'{width} px / {fps} FPS' if type(width) is int and type(fps) is int else 'Não informada'
        return result

    def build_session_information_window(self):
        dialog=QDialog(self.fullscreen_window or self);dialog.setWindowTitle('Desk · Informações da sessão');dialog.setMinimumWidth(520)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(26,24,26,22);layout.setSpacing(16)
        title=QLabel('Informações da sessão');title.setObjectName('headline');layout.addWidget(title)
        grid=QGridLayout();grid.setHorizontalSpacing(24);grid.setVerticalSpacing(11);labels={}
        for row,(name,text) in enumerate(self.session_information().items()):
            caption=QLabel(name);caption.setObjectName('muted');grid.addWidget(caption,row,0,Qt.AlignmentFlag.AlignTop)
            value=QLabel(text);value.setTextFormat(Qt.TextFormat.PlainText);value.setWordWrap(True);value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(value,row,1);labels[name]=value
        layout.addLayout(grid)
        note=QLabel('As permissões são definidas pelo computador que compartilha a tela.');note.setObjectName('muted');note.setWordWrap(True);layout.addWidget(note)
        close=QPushButton('Fechar');close.clicked.connect(dialog.accept);close.setDefault(True);layout.addWidget(close,0,Qt.AlignmentFlag.AlignRight)
        def refresh():
            for name,text in self.session_information().items():labels[name].setText(text)
        timer=QTimer(dialog);timer.setInterval(500);timer.timeout.connect(refresh);timer.start()
        dialog.information_labels=labels
        return dialog

    def show_session_information(self):
        dialog=self.build_session_information_window();dialog.exec();dialog.deleteLater()
