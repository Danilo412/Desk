from PIL import Image
from PySide6.QtPrintSupport import QPrinter
from novoacesso.printing import document_pages,paint_document,render_page

def test_image_print_to_pdf_and_pdf_rendering_without_a_physical_printer(tmp_path):
    source=tmp_path/'imagem.png';Image.new('RGB',(240,120),'#b02040').save(source)
    printer=QPrinter();printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);printer.setOutputFileName(str(tmp_path/'impresso.pdf'))
    assert paint_document(source,printer)==1
    assert document_pages(tmp_path/'impresso.pdf')==1
    image=render_page(tmp_path/'impresso.pdf',0,72)
    assert not image.isNull() and image.width()>100
