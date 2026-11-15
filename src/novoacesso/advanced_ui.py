"""Explicit recording, document tools and consented support operations."""
from pathlib import Path
import os,subprocess,threading,time
from PySide6.QtCore import Qt,QTimer,QUrl,QStandardPaths,QBuffer,QIODevice
from PySide6.QtGui import QAction,QIcon,QDesktopServices,QImage
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QToolButton,QVBoxLayout,QHBoxLayout,
    QComboBox,QCheckBox,QFileDialog,QDialog,QDialogButtonBox,QMessageBox,QListWidget,QListWidgetItem)
from .recording import VideoRecorder,LocalRecordingFeed
from .printing import PRINT_SUFFIXES

ASSETS=Path(__file__).resolve().parents[2]/'assets'

def save_bytes(path,data):
    import secrets
    path=Path(path);temporary=path.with_name('.desk-save-'+secrets.token_hex(8)+'.part')
    try:
        with temporary.open('xb') as output:output.write(data);output.flush();os.fsync(output.fileno())
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def perform_restart():
    if os.name!='nt':raise RuntimeError('O reinício remoto é compatível com Windows.')
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/shutdown.exe'
    result=subprocess.run([str(executable),'/r','/t','0'],capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('O Windows não autorizou o reinício. Verifique as permissões do usuário local.')


class AdvancedTools:
    def build_advanced_tools(self,main_menu):
        self.recorder=None;self.record_feed=None;self.record_source='';self.record_peer=None;self.recording_finishing=False
        self.annotation_overlay=None;self.pending_restart=None;self.last_received_file=None;self.remote_system_info={};self._media_frame_available=False
        self.recording_badge=QLabel();self.recording_badge.setObjectName('recordingBadge');self.recording_badge.setAccessibleName('Estado da gravação')
        header=self.status.parentWidget().layout();header.insertWidget(header.indexOf(self.status),self.recording_badge);self.recording_badge.hide()
        self.media_timer=QTimer(self);self.media_timer.setInterval(1000);self.media_timer.timeout.connect(self.refresh_recording_status);self.media_timer.start()
        self.canvas.stroke_finished.connect(self.send_annotation);self.canvas.annotation_mode_changed.connect(self.annotation_mode_finished)
        menu=self.session_tools_button.menu();menu.addSeparator()
        self.record_action=menu.addAction('Gravar sessão…',self.toggle_remote_recording)
        self.screenshot_action=menu.addAction('Capturar tela remota…',self.save_screenshot)
        self.annotation_action=menu.addAction('Anotar na tela remota');self.annotation_action.setCheckable(True);self.annotation_action.triggered.connect(self.toggle_annotations)
        self.annotation_menu=menu.addMenu('Desenho e cor');self.build_annotation_menu()
        menu.addAction('Limpar anotações',self.clear_annotations)
        menu.addSeparator();menu.addAction('Exportar conversa…',self.export_chat);menu.addAction('Exportar relatório da sessão…',self.export_session_report)
        self.folder_action=menu.addAction('Enviar pasta…',self.send_folder_dialog)
        menu.addAction('Extrair pasta recebida…',self.extract_received_folder)
        self.info_action=menu.addAction('Informações do computador remoto…',lambda:self.request_remote_operation('system_info'))
        self.print_request_action=menu.addAction('Solicitar documento remoto para imprimir…',lambda:self.request_remote_operation('print'))
        menu.addAction('Imprimir PDF ou imagem recebidos…',self.print_received_document)
        self.restart_action=menu.addAction('Reiniciar computador remoto…',lambda:self.request_remote_operation('restart'))
        self.session_record_button=QToolButton();self.session_record_button.setIcon(QIcon(str(ASSETS/'record.svg')));self.session_record_button.setObjectName('sessionTool')
        self.session_record_button.setAccessibleName('Gravar sessão remota');self.session_record_button.setToolTip('Gravar sessão remota em MP4');self.session_record_button.clicked.connect(self.toggle_remote_recording)
        row=self.image_menu_button.parentWidget().layout();row.insertWidget(row.indexOf(self.image_menu_button)+1,self.session_record_button)
        self.fullscreen_record_button=QPushButton();self.fullscreen_record_button.setIcon(QIcon(str(ASSETS/'record.svg')));self.fullscreen_record_button.setFixedWidth(34)
        self.fullscreen_record_button.setAccessibleName('Gravar sessão remota em tela cheia');self.fullscreen_record_button.setToolTip('Gravar / parar gravação da sessão');self.fullscreen_record_button.clicked.connect(self.toggle_remote_recording)
        row=self.fullscreen_tools.layout();row.insertWidget(row.indexOf(self.fullscreen_tools.details),self.fullscreen_record_button)
        self.send_folder_button=self.files_folder_button
        local=QPushButton('Gravações e ferramentas');local.clicked.connect(self.open_recordings);self.session_side.widget(2).layout().addWidget(local)
        self.build_recordings_page()
        action=QAction('Gravações e ferramentas',main_menu);action.triggered.connect(self.open_recordings);main_menu.insertAction(main_menu.actions()[-1],action)
        self.update_advanced_actions()

    def build_recordings_page(self):
        page=QWidget();col=QVBoxLayout(page);col.setContentsMargins(28,24,28,24);col.setSpacing(16)
        title=QLabel('Gravações e ferramentas');title.setObjectName('headline');col.addWidget(title)
        note=QLabel('Grave sua tela ou a sessão remota em MP4. O áudio do sistema é opcional. Microfone não é capturado.');note.setWordWrap(True);note.setObjectName('muted');col.addWidget(note)
        row=QHBoxLayout();self.local_record_button=QPushButton('Gravar minha tela…');self.local_record_button.setObjectName('primary');self.local_record_button.clicked.connect(self.start_local_recording_dialog);row.addWidget(self.local_record_button)
        self.pause_record_button=QPushButton('Pausar');self.pause_record_button.clicked.connect(self.pause_recording);row.addWidget(self.pause_record_button)
        self.stop_record_button=QPushButton('Parar e salvar');self.stop_record_button.clicked.connect(self.stop_recording);row.addWidget(self.stop_record_button);row.addStretch();col.addLayout(row)
        self.record_status=QLabel('Nenhuma gravação em andamento.');self.record_status.setWordWrap(True);col.addWidget(self.record_status)
        self.recording_list=QListWidget();self.recording_list.setAccessibleName('Gravações salvas neste computador');col.addWidget(self.recording_list,1)
        self.recording_list.itemDoubleClicked.connect(lambda item:self.play_recording())
        row=QHBoxLayout()
        for text,callback in [('Reproduzir vídeo',self.play_recording),('Abrir pasta de gravações',self.open_recording_folder),('Atualizar lista',self.refresh_recording_list)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();col.addLayout(row)
        row=QHBoxLayout()
        for text,callback in [('Exportar conversa',self.export_chat),('Imprimir PDF ou imagem',self.print_received_document),('Extrair pasta recebida',self.extract_received_folder)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();col.addLayout(row);self.recordings_page=page;self.tabs.addTab(page,'Gravações e ferramentas');self.refresh_recording_list();self.refresh_recording_status()

    def open_recordings(self):self.tabs.setCurrentWidget(self.recordings_page);self.refresh_recording_list()

    def recording_directory(self):
        if os.environ.get('NOVOACESSO_STATE_DIR'):
            directory=Path(os.environ['NOVOACESSO_STATE_DIR'])/'recordings';directory.mkdir(parents=True,exist_ok=True);return directory
        directory=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or str(Path.home()/'Videos'))/'Desk'
        directory.mkdir(parents=True,exist_ok=True);return directory

    def refresh_recording_list(self):
        if not hasattr(self,'recording_list'):return
        self.recording_list.clear();paths={str(p) for p in self.recording_directory().glob('*.mp4')}
        paths.update(p for p in self.identity.settings().get('recording_history',[]) if isinstance(p,str) and Path(p).suffix.lower()=='.mp4')
        files=[Path(p) for p in paths if Path(p).is_file()]
        for path in sorted(files,key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
            item=QListWidgetItem(path.name+'\n'+time.strftime('%d/%m/%Y %H:%M',time.localtime(path.stat().st_mtime))+f' · {path.stat().st_size/1024/1024:.1f} MB')
            item.setData(Qt.ItemDataRole.UserRole,str(path));self.recording_list.addItem(item)

    def play_recording(self):
        item=self.recording_list.currentItem()
        if item:
            path=Path(item.data(Qt.ItemDataRole.UserRole))
            if path.is_file() and path.suffix.lower()=='.mp4':QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_recording_folder(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.recording_directory())))

    def recording_options(self,local):
        if self.recorder:self.open_recordings();return None
        if not local and (not self.peer or self.peer.role!='viewer' or self.canvas.image is None):self.notice('Conecte e aguarde a tela remota antes de gravar.');return None
        dialog=QDialog(self.fullscreen_window or self);dialog.setWindowTitle('Desk · Gravar minha tela' if local else 'Desk · Gravar sessão remota');dialog.setMinimumWidth(470)
        col=QVBoxLayout(dialog);col.setContentsMargins(24,22,24,22);col.setSpacing(12)
        heading=QLabel('Gravar minha tela' if local else 'Gravar a tela recebida');heading.setObjectName('connectorName');col.addWidget(heading)
        monitor=QComboBox();monitor.setAccessibleName('Monitor para gravar')
        if local:
            try:
                import mss
                with mss.MSS() as source:
                    for index,rect in enumerate(source.monitors):monitor.addItem(('Todas as telas' if index==0 else f'Monitor {index}')+f" · {rect['width']} × {rect['height']}",index)
                monitor.setCurrentIndex(1 if monitor.count()>1 else 0)
            except Exception as ex:self.notice('Não foi possível listar os monitores: '+str(ex)[:120]);dialog.deleteLater();return None
            col.addWidget(QLabel('Tela para gravar'));col.addWidget(monitor)
        profile=QComboBox();profile.addItem('Melhor qualidade · até 1440p / 30 FPS',(2560,30));profile.addItem('Full HD · até 1080p / 30 FPS',(1920,30));profile.addItem('Mais leve · até 1080p / 15 FPS',(1920,15));col.addWidget(profile)
        audio=QCheckBox('Incluir áudio do sistema' if local else 'Incluir o áudio autorizado da sessão')
        audio.setEnabled(local or bool(self.peer.permissions.get('audio')));col.addWidget(audio)
        note=QLabel('A gravação permanece neste computador. Você pode pausar e encerrar a qualquer momento. A resolução do vídeo é definida pela primeira imagem; mudanças de tela são ajustadas a esse tamanho.');note.setWordWrap(True);note.setObjectName('muted');col.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Save).setText('Escolher arquivo e gravar')
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);col.addWidget(buttons)
        allowed=dialog.exec()==QDialog.DialogCode.Accepted
        result=dict(monitor=monitor.currentData(),width=profile.currentData()[0],fps=profile.currentData()[1],audio=audio.isChecked()) if allowed else None
        dialog.deleteLater();return result

    def start_local_recording_dialog(self):self.begin_recording_dialog(True)
    def toggle_remote_recording(self):
        if self.recorder and self.record_source=='remote':self.stop_recording();return
        self.begin_recording_dialog(False)

    def begin_recording_dialog(self,local):
        options=self.recording_options(local)
        if options is None:return
        path,_=QFileDialog.getSaveFileName(self.fullscreen_window or self,'Salvar gravação MP4',str(self.recording_directory()/time.strftime('Desk-%Y%m%d-%H%M%S.mp4')),'Vídeo MP4 (*.mp4)')
        if not path:return
        if not Path(path).suffix:path+='.mp4'
        try:self.begin_recording(path,'local' if local else 'remote',**options)
        except (ValueError,OSError) as ex:self.notice(str(ex))

    def begin_recording(self,path,source,monitor=1,width=2560,fps=30,audio=False):
        if self.recorder:raise ValueError('Encerre a gravação atual antes de iniciar outra.')
        if source not in ('local','remote'):raise ValueError('Fonte de gravação inválida.')
        if source=='remote' and (not self.peer or self.peer.role!='viewer' or self.canvas.image is None):raise ValueError('Não há tela remota disponível para gravar.')
        if source=='remote' and audio and not self.peer.permissions.get('audio'):raise ValueError('A outra ponta não autorizou áudio.')
        self.record_source=source;self.record_peer=self.peer if source=='remote' else None;self.recording_finishing=False
        self.recorder=VideoRecorder(path,self.emit_event,fps=fps,max_width=width,audio=audio).start()
        if source=='local':self.record_feed=LocalRecordingFeed(self.recorder,monitor).start()
        else:
            if audio:self.peer.recording_audio_sink=self.recorder.offer_audio
            self.recorder.offer(self._canvas_pil_image())
        self.refresh_recording_status();self.update_advanced_actions()

    def _canvas_pil_image(self):
        from PIL import Image
        image=self.canvas.image.convertToFormat(QImage.Format.Format_RGB888)
        return Image.frombytes('RGB',(image.width(),image.height()),bytes(image.constBits()),'raw','RGB',image.bytesPerLine())

    def on_advanced_frame(self,image):
        if not self._media_frame_available:self._media_frame_available=True;self.update_advanced_actions()
        if self.recorder and self.record_source=='remote' and self.peer is self.record_peer and not self.recording_finishing:self.recorder.offer(image)

    def pause_recording(self):
        if self.recorder and not self.recording_finishing:self.recorder.pause(not self.recorder.paused);self.refresh_recording_status()

    def stop_recording(self):
        if not self.recorder:return
        if self.record_feed:self.record_feed.stop();self.record_feed=None
        if self.record_peer:self.record_peer.recording_audio_sink=None
        self.recording_finishing=True;self.recorder.stop();self.refresh_recording_status();self.update_advanced_actions()

    def refresh_recording_status(self):
        if not hasattr(self,'record_status'):return
        active=bool(self.recorder);self.pause_record_button.setEnabled(active and not self.recording_finishing);self.stop_record_button.setEnabled(active and not self.recording_finishing);self.local_record_button.setEnabled(not active)
        self.recording_badge.setVisible(active)
        if active:
            seconds=int(self.recorder.elapsed);duration=f'{seconds//60:02d}:{seconds%60:02d}'
            text='Finalizando gravação…' if self.recording_finishing else ('Ⅱ Pausado ' if self.recorder.paused else '● Gravando ')+duration
            self.recording_badge.setText(text);self.recording_badge.setStyleSheet('color:#ff756b;background:transparent;padding:3px 8px;font-weight:600;')
            self.record_status.setText(text+' · '+('sua tela' if self.record_source=='local' else 'sessão remota'))
            self.pause_record_button.setText('Continuar' if self.recorder.paused else 'Pausar')

    def save_screenshot(self):
        if not self.peer or self.peer.role!='viewer' or self.canvas.image is None:self.notice('Aguarde a imagem remota para capturar a tela.');return
        image=self.canvas.snapshot();path,_=QFileDialog.getSaveFileName(self.fullscreen_window or self,'Salvar captura da tela remota',str(Path.home()/time.strftime('Desk-captura-%Y%m%d-%H%M%S.png')),'Imagem PNG (*.png)')
        if not path:return
        if not Path(path).suffix:path+='.png'
        buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer,'PNG'):self.notice('Não foi possível gerar a captura.');return
        save_bytes(path,bytes(buffer.data()));self.activity.setText('Captura salva: '+Path(path).name)

    def export_chat(self):
        text=self.chat.toPlainText()
        if not text.strip():self.notice('A conversa ainda está vazia.');return
        path,_=QFileDialog.getSaveFileName(self.fullscreen_window or self,'Exportar conversa',str(Path.home()/time.strftime('Desk-conversa-%Y%m%d-%H%M%S.txt')),'Texto UTF-8 (*.txt)')
        if path:save_bytes(path,('Desk · conversa exportada\n\n'+text+'\n').encode('utf-8'));self.activity.setText('Conversa exportada: '+Path(path).name)

    def export_session_report(self):
        values=self.session_information();values.update(self.remote_system_info)
        path,_=QFileDialog.getSaveFileName(self.fullscreen_window or self,'Exportar relatório da sessão',str(Path.home()/time.strftime('Desk-sessao-%Y%m%d-%H%M%S.txt')),'Texto UTF-8 (*.txt)')
        if path:save_bytes(path,('Desk · relatório da sessão\n'+time.strftime('%d/%m/%Y %H:%M')+'\n\n'+'\n'.join(f'{k}: {v}' for k,v in values.items())+'\n').encode('utf-8'));self.activity.setText('Relatório exportado: '+Path(path).name)

    def send_folder_dialog(self):
        if not self.peer:return
        peer=self.peer;path=QFileDialog.getExistingDirectory(self.fullscreen_window or self,'Selecionar pasta para enviar · até 250 MB')
        if path and self.peer is peer and not peer.closed.is_set():self.send_paths([path])

    def extract_received_folder(self):
        path=self.last_received_file
        if path is None or path.suffix.lower()!='.zip':
            value,_=QFileDialog.getOpenFileName(self.fullscreen_window or self,'Selecionar pacote de pasta recebido','','Pacote ZIP (*.zip)');path=Path(value) if value else None
        if path is None:return
        parent=QFileDialog.getExistingDirectory(self.fullscreen_window or self,'Escolher onde extrair a pasta')
        if not parent:return
        self.activity.setText('Conferindo e extraindo a pasta…')
        def worker():
            try:
                from .folders import extract_folder
                result=extract_folder(path,parent);self.emit_event('local_operation_done',dict(text='Pasta extraída: '+result.name))
            except Exception as ex:self.emit_event('local_operation_done',dict(text='Não foi possível extrair a pasta: '+str(ex)[:180]))
        threading.Thread(target=worker,name='Desk folder extraction',daemon=False).start()

    def print_received_document(self):
        path=self.last_received_file
        if path is None or path.suffix.lower() not in PRINT_SUFFIXES:
            value,_=QFileDialog.getOpenFileName(self.fullscreen_window or self,'Selecionar PDF ou imagem para imprimir','','PDF e imagens (*.pdf *.png *.jpg *.jpeg *.bmp *.webp)');path=Path(value) if value else None
        if path is None:return
        try:
            from .printing import print_document
            if print_document(path,self.fullscreen_window or self):self.activity.setText('Documento enviado à impressora escolhida.')
        except Exception as ex:self.notice('Impressão: '+str(ex)[:200])

    def request_remote_operation(self,operation):
        try:
            if not self.peer:return
            if operation=='whiteboard' and self.monitor.currentData()==0 and self.monitor.count()>2:raise ValueError('Selecione um monitor individual antes de anotar.')
            self.peer.features.request(operation);self.activity.setText('Aguardando autorização no computador remoto…')
        except (ValueError,AttributeError) as ex:self.notice(str(ex));self.annotation_mode_finished(False)

    def advanced_prompt(self,prompt):
        peer=prompt.data.get('_peer');operation=prompt.data.get('operation')
        def valid():return self.peer is peer and peer is not None and peer.role=='host' and not peer.closed.is_set() and not prompt.is_cancelled() and not self.closing
        if not valid():return False
        if operation in ('restart','whiteboard') and not peer.permissions.get('control'):return False
        if operation=='whiteboard' and peer.monitor==0 and len(peer.monitors)>2:return False
        if operation=='print':
            dialog=QFileDialog(self,'Enviar documento para impressão na outra máquina',str(Path.home()));dialog.setOption(QFileDialog.Option.DontUseNativeDialog,True)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile);dialog.setNameFilter('PDF e imagens (*.pdf *.png *.jpg *.jpeg *.bmp *.webp)')
        else:
            messages={'system_info':('Compartilhar informações técnicas?','A outra ponta solicita nome do computador, versão do Windows, processador, memória, espaço livre e quantidade de monitores.'),
                      'restart':('Permitir reinício deste computador?','Salve seu trabalho. Após o aceite haverá uma contagem de 30 segundos que você poderá cancelar. O Windows poderá pedir para fechar programas. O Desk volta após o login se a inicialização com o Windows estiver configurada.'),
                      'whiteboard':('Permitir anotações na sua tela?','A outra ponta poderá desenhar indicações sobre o monitor compartilhado durante esta sessão. Revogar Mouse e teclado também remove essa permissão.')}
            if operation not in messages:return False
            title,text=messages[operation];dialog=QMessageBox(QMessageBox.Icon.Question,title,text,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,self)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
        timer=QTimer(dialog);timer.setInterval(75);timer.timeout.connect(lambda:dialog.reject() if not valid() else None);timer.start()
        self.notifications.prepare_dialog(dialog)
        result=dialog.exec();allowed=valid() and result==(QDialog.DialogCode.Accepted if operation=='print' else QMessageBox.StandardButton.Yes)
        answer=dialog.selectedFiles()[0] if allowed and operation=='print' and dialog.selectedFiles() else allowed
        dialog.deleteLater()
        if allowed and operation=='restart':return self.schedule_remote_restart(peer)
        return answer

    def schedule_remote_restart(self,peer):
        if self.pending_restart:return False
        if self.peer is not peer or peer.closed.is_set() or not peer.permissions.get('control'):return False
        dialog=QDialog(self);dialog.setWindowTitle('Desk · Reinício solicitado');col=QVBoxLayout(dialog);label=QLabel();label.setWordWrap(True);col.addWidget(label)
        cancel=QPushButton('Cancelar reinício');cancel.clicked.connect(self.cancel_remote_restart);col.addWidget(cancel)
        timer=QTimer(dialog);timer.setInterval(200);job=dict(peer=peer,dialog=dialog,timer=timer,label=label,deadline=time.monotonic()+30)
        self.pending_restart=job
        def tick():
            if self.pending_restart is not job:return
            if self.peer is not peer or peer.closed.is_set() or not peer.permissions.get('control'):self.cancel_remote_restart();return
            remaining=max(0,int(job['deadline']-time.monotonic()+.99));label.setText(f'Reinício confirmado para daqui a {remaining} segundos. Salve seus arquivos. Você pode cancelar abaixo.')
            if not remaining:
                timer.stop();self.pending_restart=None;dialog.close();dialog.deleteLater();self.stop_recording()
                if self.recorder and not self.recorder.wait(8):self.notice('A gravação ainda está finalizando. O reinício foi cancelado para preservar o vídeo.');return
                try:perform_restart()
                except Exception as ex:self.notice(str(ex))
        dialog.rejected.connect(self.cancel_remote_restart);timer.timeout.connect(tick);tick();timer.start();dialog.show();return True

    def cancel_remote_restart(self):
        job=self.pending_restart
        if not job:return
        self.pending_restart=None;job['timer'].stop();job['dialog'].close();job['dialog'].deleteLater();self.activity.setText('Reinício cancelado.')

    def build_annotation_menu(self):
        from PySide6.QtGui import QActionGroup
        shapes=QActionGroup(self);shapes.setExclusive(True)
        for key,label in [('freehand','Mão livre'),('line','Linha'),('rectangle','Retângulo'),('ellipse','Círculo'),('arrow','Seta')]:
            action=self.annotation_menu.addAction(label);action.setCheckable(True);action.setChecked(key=='freehand');shapes.addAction(action);action.triggered.connect(lambda checked=False,k=key:setattr(self.canvas,'annotation_shape',k))
        self.annotation_menu.addSeparator();colors=QActionGroup(self);colors.setExclusive(True)
        for value,label in [('#ef443b','Vermelho'),('#ffc857','Amarelo'),('#57bd7a','Verde'),('#59a8ff','Azul'),('#e6e6e6','Branco'),('#151515','Preto')]:
            action=self.annotation_menu.addAction(label);action.setCheckable(True);action.setChecked(value=='#ef443b');colors.addAction(action);action.triggered.connect(lambda checked=False,v=value:setattr(self.canvas,'annotation_color',v))

    def toggle_annotations(self,checked):
        if not checked:self.canvas.set_annotation_mode(False);return
        if self.peer and getattr(self.peer,'features',None) and self.peer.features.viewer_whiteboard:self.canvas.set_annotation_mode(True)
        else:self.request_remote_operation('whiteboard')

    def annotation_mode_finished(self,enabled):
        self.annotation_action.blockSignals(True);self.annotation_action.setChecked(enabled);self.annotation_action.blockSignals(False)
        if not enabled:self.canvas.set_annotation_mode(False)

    def send_annotation(self,stroke):
        if self.peer and getattr(self.peer,'features',None):self.peer.features.send_stroke(stroke)

    def clear_annotations(self):
        self.canvas.annotations.clear();self.canvas.current_stroke=None;self.canvas.update()
        if self.peer and getattr(self.peer,'features',None):self.peer.features.clear()
        if self.annotation_overlay:self.annotation_overlay.clear()

    def update_advanced_actions(self):
        if not hasattr(self,'record_action'):return
        peer=self.peer;closed=getattr(peer,'closed',None);connected=bool(peer and not (closed and closed.is_set()));viewer=connected and peer.role=='viewer';frame=viewer and self.canvas.image is not None
        active_remote=bool(self.recorder and self.record_source=='remote');can_record=(frame and self.recorder is None) or (active_remote and not self.recording_finishing)
        for button in (self.record_action,self.session_record_button,self.fullscreen_record_button):button.setEnabled(bool(can_record))
        self.record_action.setText('Parar e salvar gravação' if active_remote else 'Gravar sessão…')
        self.screenshot_action.setEnabled(bool(frame));self.folder_action.setEnabled(connected);self.send_folder_button.setEnabled(connected)
        capabilities=getattr(peer,'remote_capabilities',set()) if peer else set()
        self.info_action.setEnabled(viewer and 'system_info' in capabilities);self.print_request_action.setEnabled(viewer and 'print' in capabilities)
        self.restart_action.setEnabled(viewer and 'restart' in capabilities and bool(getattr(peer,'permissions',{}).get('control')))
        self.annotation_action.setEnabled(viewer and frame and 'whiteboard' in capabilities and bool(getattr(peer,'permissions',{}).get('control')))
        self.annotation_menu.setEnabled(self.annotation_action.isEnabled())

    def on_advanced_event(self,name,data):
        if not hasattr(self,'record_action'):return
        if name=='recording_done':
            if not self.recorder or self.recorder.id!=data.get('id'):return
            if self.record_feed:self.record_feed.stop();self.record_feed=None
            if self.record_peer:self.record_peer.recording_audio_sink=None
            self.recorder=None;self.record_peer=None;self.record_source='';self.recording_finishing=False
            if data.get('success'):
                history=self.identity.settings().get('recording_history',[]);self.identity.configure(recording_history=[data['path'],*[p for p in history if p!=data['path']]][:100])
                text='Gravação salva: '+Path(data['path']).name
                if data.get('warning'):text+=' · '+data['warning']
            else:text='Não foi possível salvar a gravação: '+data.get('error','falha desconhecida')
            self.record_status.setText(text);self.activity.setText(text);self.refresh_recording_status();self.refresh_recording_list()
        elif name=='file_received':self.last_received_file=Path(data['path']);self.activity.setText('Arquivo recebido. Use Ferramentas para extrair uma pasta ZIP ou imprimir PDF e imagens.')
        elif name=='local_operation_done':self.activity.setText(data['text'])
        elif name=='advanced_result':
            labels={'accepted':'Solicitação aceita.','declined':'A outra ponta recusou ou cancelou a solicitação.','busy':'A outra ponta está respondendo a outra solicitação.','failed':'A função não foi concluída. Confira se as duas máquinas usam o Desk atualizado.'}
            self.activity.setText(labels[data['status']])
            if data['status']=='accepted' and data['operation']=='system_info':self.remote_system_info=data['values'];self.show_remote_information()
            elif data['operation']=='whiteboard':
                enabled=data['status']=='accepted';self.canvas.set_annotation_mode(enabled);self.annotation_mode_finished(enabled)
                if enabled:self.activity.setText('Anotações autorizadas. Desenhe na imagem; Esc sai do desenho. Use Ferramentas para mudar forma e cor.')
            elif data['status']=='accepted' and data['operation']=='print':self.activity.setText('O documento será enviado como arquivo. Após recebê-lo, use Ferramentas > Imprimir PDF ou imagem recebidos.')
        elif name=='annotation':
            peer=data.get('peer')
            if self.peer is peer and peer.role=='host' and peer.permissions.get('control') and peer.backend and peer.backend.rect:
                try:
                    from .annotations import AnnotationOverlay
                    if self.annotation_overlay is None:self.annotation_overlay=AnnotationOverlay()
                    self.annotation_overlay.add_stroke(data['stroke'],dict(peer.backend.rect))
                except Exception as ex:self.activity.setText(str(ex)[:180])
        elif name in ('annotation_clear','whiteboard_disabled'):
            if self.annotation_overlay:self.annotation_overlay.clear()
            if name=='whiteboard_disabled':self.canvas.annotations.clear();self.annotation_mode_finished(False)
        elif name in ('connected','disconnected'):
            self._media_frame_available=False;self.remote_system_info={};self.clear_annotations();self.annotation_mode_finished(False)
            if name=='disconnected':
                if self.record_source=='remote':self.stop_recording()
                self.cancel_remote_restart()
        elif name=='permissions':
            if self.peer and not self.peer.permissions.get('control'):self.annotation_mode_finished(False);self.clear_annotations();self.cancel_remote_restart()
        self.update_advanced_actions()

    def show_remote_information(self):
        dialog=QDialog(self.fullscreen_window or self);dialog.setWindowTitle('Desk · Computador remoto');dialog.setMinimumWidth(520);col=QVBoxLayout(dialog)
        title=QLabel('Informações autorizadas pelo computador remoto');title.setWordWrap(True);title.setObjectName('connectorName');col.addWidget(title)
        for key,value in self.remote_system_info.items():
            label=QLabel(key+': '+value);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);col.addWidget(label)
        button=QPushButton('Exportar relatório…');button.clicked.connect(self.export_session_report);col.addWidget(button)
        close=QPushButton('Fechar');close.clicked.connect(dialog.accept);col.addWidget(close);dialog.exec();dialog.deleteLater()

    def shutdown_advanced(self):
        if not hasattr(self,'recorder'):return
        self.cancel_remote_restart();self.stop_recording()
        if self.recorder:self.recorder.wait(8)
        if self.annotation_overlay:self.annotation_overlay.close();self.annotation_overlay.deleteLater();self.annotation_overlay=None
