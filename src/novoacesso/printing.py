"""Local print dialog for explicitly received/selected PDFs and images."""
from pathlib import Path
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QImage,QImageReader,QPainter
from PySide6.QtWidgets import QDialog
from PySide6.QtPrintSupport import QPrinter,QPrintDialog

PRINT_SUFFIXES={'.pdf','.png','.jpg','.jpeg','.bmp','.webp'}

def document_pages(path):
    path=Path(path)
    if path.suffix.lower() not in PRINT_SUFFIXES:raise ValueError('Escolha um PDF ou uma imagem para imprimir.')
    if path.suffix.lower()=='.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as document:
            pages=len(document)
            if not 1<=pages<=5000:raise ValueError('Quantidade de páginas não suportada.')
            return pages
    reader=QImageReader(str(path));size=reader.size()
    if not size.isValid() or size.width()*size.height()>40_000_000:raise ValueError('Imagem inválida ou grande demais para imprimir.')
    return 1

def render_page(path,index=0,dpi=150):
    path=Path(path)
    if path.suffix.lower()=='.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as document:
            page=document[index]
            try:
                width,height=page.get_size()
                if min(width,height)<=0 or max(width,height)>20000:raise ValueError('Tamanho de página inválido.')
                bitmap=page.render(scale=min(dpi/72,4096/width,4096/height))
                try:
                    image=bitmap.to_pil().convert('RGB');raw=image.tobytes()
                    return QImage(raw,image.width,image.height,image.width*3,QImage.Format.Format_RGB888).copy()
                finally:bitmap.close()
            finally:page.close()
    image=QImage(str(path))
    if image.isNull():raise ValueError('Não foi possível abrir a imagem para impressão.')
    return image

def paint_document(path,printer,first=1,last=None):
    pages=document_pages(path);last=pages if last is None else min(pages,last)
    if not 1<=first<=last:raise ValueError('Intervalo de páginas inválido.')
    painter=QPainter()
    if not painter.begin(printer):raise RuntimeError('Não foi possível iniciar a impressão.')
    try:
        for index in range(first-1,last):
            if index>first-1 and not printer.newPage():raise RuntimeError('A impressora recusou a próxima página.')
            image=render_page(path,index,min(300,printer.resolution()))
            rect=QRectF(printer.pageRect(QPrinter.Unit.DevicePixel))
            size=image.size().scaled(rect.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRectF(rect.x()+(rect.width()-size.width())/2,rect.y()+(rect.height()-size.height())/2,size.width(),size.height())
            painter.drawImage(target,image)
    finally:painter.end()
    return last-first+1

def print_document(path,parent=None):
    pages=document_pages(path);printer=QPrinter(QPrinter.PrinterMode.HighResolution);printer.setDocName(Path(path).name)
    dialog=QPrintDialog(printer,parent);dialog.setWindowTitle('Desk · Imprimir arquivo recebido');dialog.setMinMax(1,pages)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return False
    first=printer.fromPage() or 1;last=printer.toPage() or pages
    paint_document(path,printer,first,last);return True
