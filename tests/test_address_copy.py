from PySide6.QtCore import Qt,QEvent,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from novoacesso.app import MainWindow


def test_address_hover_does_not_copy_and_click_copies_only_fixed_number(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.show();QTest.qWait(30)
    try:
        field=window.numeric_code;field.setText('1234 5678 9012');window.invite.setPlainText('NA1-private-invitation')
        QApplication.clipboard().setText('clipboard-before-hover')
        QApplication.sendEvent(field,QEvent(QEvent.Type.Enter))
        assert QApplication.clipboard().text()=='clipboard-before-hover'
        assert field.cursor().shape()==Qt.CursorShape.PointingHandCursor and 'Clique para copiar' in field.toolTip()
        QTest.mouseClick(field,Qt.MouseButton.LeftButton,pos=field.rect().center())
        assert QApplication.clipboard().text()=='1234 5678 9012'
        assert field.property('copied') is True and field.toolTip()=='Endereço copiado'
        window.reset_copy_feedback();assert field.property('copied') is False
        assert not window.connecting and window.peer is None
    finally:window.close();QTest.qWait(30)


def test_address_keyboard_copy_and_drag_selection_preserve_expected_behavior(tmp_path,monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR',str(tmp_path));window=MainWindow();window.show();QTest.qWait(30)
    try:
        field=window.numeric_code;field.setText('1234 5678 9012');field.setFocus()
        for key in (Qt.Key.Key_Return,Qt.Key.Key_Space):
            QApplication.clipboard().setText('before-key');QTest.keyClick(field,key)
            assert QApplication.clipboard().text()=='1234 5678 9012'
        QApplication.clipboard().setText('before-drag')
        QTest.mousePress(field,Qt.MouseButton.LeftButton,pos=QPoint(40,field.height()//2))
        QTest.mouseMove(field,QPoint(field.width()-40,field.height()//2))
        QTest.mouseRelease(field,Qt.MouseButton.LeftButton,pos=QPoint(field.width()-40,field.height()//2))
        assert QApplication.clipboard().text()=='before-drag'
        field.setText('');QTest.mouseClick(field,Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text()=='before-drag' and not window.connecting
    finally:window.close();QTest.qWait(30)
