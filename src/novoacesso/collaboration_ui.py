"""Session-only chat timestamps and truthful local transfer activity."""
import time
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,QProgressBar,QPlainTextEdit

def local_file_paths(mime):
    urls=mime.urls() if mime.hasUrls() else []
    if not 1<=len(urls)<=32 or any(not url.isLocalFile() for url in urls):return []
    return list(dict.fromkeys(url.toLocalFile() for url in urls))

class FileDropArea(QFrame):
    files_dropped=Signal(list)
    def __init__(self):
        super().__init__();self.setAcceptDrops(True);self.setObjectName('fileDropArea')
        col=QVBoxLayout(self);label=QLabel('Arraste arquivos ou pastas aqui\nou escolha o que deseja enviar.');label.setWordWrap(True);label.setAlignment(Qt.AlignmentFlag.AlignCenter);col.addWidget(label)
        self.setAccessibleName('Soltar arquivos ou pastas para enviar');self.setMinimumHeight(76)
        self.setStyleSheet('QFrame#fileDropArea{border:1px dashed #777;border-radius:5px;background:#282828;} QFrame#fileDropArea QLabel{border:0;background:transparent;color:#bbb;}')
    def dragEnterEvent(self,event):
        if self.isEnabled() and local_file_paths(event.mimeData()):event.acceptProposedAction()
        else:event.ignore()
    def dropEvent(self,event):
        paths=local_file_paths(event.mimeData())
        if self.isEnabled() and paths:self.files_dropped.emit(paths);event.acceptProposedAction()
        else:event.ignore()

class SessionChat(QPlainTextEdit):
    def appendPlainText(self,text):
        super().appendPlainText(time.strftime('[%H:%M] ')+str(text))

class TransferPanel(QWidget):
    TERMINAL={'sent','verified','declined','failed','interrupted'}
    STATES={'hashing':'Preparando','waiting':'Aguardando aceite','sending':'Enviando','receiving':'Recebendo',
            'sent':'Envio concluído','verified':'Recebido e conferido','declined':'Recusado ou expirado','failed':'Falha','interrupted':'Interrompido'}
    def __init__(self,parent=None):
        super().__init__(parent);self.records={};self.items={};col=QVBoxLayout(self);col.setContentsMargins(0,0,0,0);col.setSpacing(8)
        row=QHBoxLayout();row.addWidget(QLabel('Transferências desta sessão'));row.addStretch()
        self.clear_button=QPushButton('Limpar');self.clear_button.setObjectName('textAction');self.clear_button.setToolTip('Retirar registros concluídos da lista; os arquivos são mantidos.');self.clear_button.clicked.connect(self.clear_finished);row.addWidget(self.clear_button);col.addLayout(row)
        self.list=QListWidget();self.list.setAccessibleName('Histórico de transferências');self.list.setMinimumHeight(110);col.addWidget(self.list,1)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setTextVisible(False);self.progress.setFixedHeight(5);col.addWidget(self.progress)
        self.detail=QLabel('Nenhum arquivo transferido.');self.detail.setTextFormat(Qt.TextFormat.PlainText);self.detail.setWordWrap(True);self.detail.setObjectName('muted');col.addWidget(self.detail)
        self.list.currentItemChanged.connect(lambda *a:self.refresh_detail())

    @staticmethod
    def size(value):
        return f'{value/1024/1024:.1f} MB' if value>=1024*1024 else f'{value/1024:.1f} KB'

    def update_transfer(self,data):
        transfer=data.get('id');state=data.get('state');direction=data.get('direction')
        if not isinstance(transfer,str) or len(transfer)!=16 or state not in self.STATES or direction not in ('send','receive'):return
        id=direction+':'+transfer
        if id not in self.records:
            if len(self.records)>=100:
                removable=next((k for k,v in self.records.items() if v['state'] in self.TERMINAL),None)
                if removable is None:return
                self.remove_record(removable)
            self.records[id]={};item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,id);self.items[id]=item;self.list.addItem(item)
        item=self.items[id];self.records[id].update(data);record=self.records[id]
        size=max(0,int(record.get('size',0)));done=max(0,min(size,int(record.get('done',0))))
        direction='Enviando' if record.get('direction')=='send' else 'Recebendo'
        status=self.STATES[state]
        item.setText(str(record.get('name','Arquivo'))+'\n'+status+' · '+self.size(done)+' / '+self.size(size))
        item.setToolTip(direction+' · '+str(record.get('name','Arquivo'))+'\n'+status)
        if self.list.currentItem() is None:self.list.setCurrentItem(item)
        self.refresh_detail()

    def refresh_detail(self):
        item=self.list.currentItem()
        if not item:self.progress.setValue(0);self.detail.setText('Nenhum arquivo transferido.');return
        record=self.records.get(item.data(Qt.ItemDataRole.UserRole),{});size=max(0,record.get('size',0));done=max(0,min(size,record.get('done',0)))
        self.progress.setValue(int(100*done/size) if size else (100 if record.get('state') in ('sent','verified') else 0))
        text=self.STATES.get(record.get('state'),'')
        if record.get('state')=='sent':text+=' pela conexão. O recebimento é conferido na outra ponta.'
        elif record.get('state')=='verified':text+=': integridade verificada e arquivo salvo.'
        self.detail.setText(text)

    def remove_record(self,id):
        item=self.items.pop(id);self.list.takeItem(self.list.row(item));self.records.pop(id,None)

    def clear_finished(self):
        for id in list(self.records):
            if self.records[id]['state'] in self.TERMINAL:self.remove_record(id)
        self.refresh_detail()

    def interrupt_pending(self):
        for id,record in list(self.records.items()):
            if record['state'] not in self.TERMINAL:self.update_transfer(dict(record,state='interrupted'))

class CollaborationTools:
    def mark_chat_read(self,*args):
        if not hasattr(self,'session_side'):return
        if self.tabs.currentIndex()==1 and self.session_side.isVisible() and self.session_side.currentIndex()==0:
            self._unread_chat=0;self.refresh_chat_badge()

    def refresh_chat_badge(self):
        value=getattr(self,'_unread_chat',0);suffix='99+' if value>99 else str(value)
        self.session_side.setTabText(0,'Conversa'+(' ('+suffix+')' if value else ''))
        self.session_sidebar_button.setText('Conversa ('+suffix+')' if value else 'Conversa')

    def on_collaboration_event(self,name,data):
        if name=='chat':
            visible=self.tabs.currentIndex()==1 and self.session_side.isVisible() and self.session_side.currentIndex()==0
            if not visible:self._unread_chat=min(100,getattr(self,'_unread_chat',0)+1)
            self.refresh_chat_badge()
        elif name=='transfer':self.transfer_panel.update_transfer(data)
        elif name=='disconnected':self.transfer_panel.interrupt_pending()
