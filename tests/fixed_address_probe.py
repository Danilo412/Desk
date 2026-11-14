"""Fresh-process GUI lifecycle probe, always using a caller-supplied test state."""
import os,sys,json
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['NOVOACESSO_OFFLINE']='1'
os.environ['NOVOACESSO_STATE_DIR']=sys.argv[1];os.environ['DESK_AUTOREADY']='0'
from PySide6.QtWidgets import QApplication
from novoacesso.app import MainWindow
app=QApplication([]);window=MainWindow();before=window.numeric_code.text()
window.disconnect();after=window.numeric_code.text();window.close();app.processEvents()
print(json.dumps({'pid':os.getpid(),'before':before,'after_disconnect':after}))
