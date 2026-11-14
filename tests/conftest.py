import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['NOVOACESSO_OFFLINE']='1'
import pytest
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope='session',autouse=True)
def application_lifetime(tmp_path_factory):
    """Uma única QApplication, criada antes dos trabalhadores, como no aplicativo."""
    app=QApplication.instance() or QApplication([])
    previous=os.environ.get('NOVOACESSO_STATE_DIR');os.environ['NOVOACESSO_STATE_DIR']=str(tmp_path_factory.mktemp('ui-state'))
    yield app
    app.processEvents()
    if previous is None:os.environ.pop('NOVOACESSO_STATE_DIR',None)
    else:os.environ['NOVOACESSO_STATE_DIR']=previous
