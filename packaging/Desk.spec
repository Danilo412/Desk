from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files,collect_submodules
base=Path(SPECPATH);project=base.parent
sys.path.insert(0,str(project/'src'))
hidden=collect_submodules('novoacesso')+collect_submodules('metered_realtime')
hidden+=['soundcard','comtypes.client','comtypes.stream','comtypes.persist','dxcam','numpy','av']
a=Analysis([str(project/'iniciar.py')],pathex=[str(project/'src')],binaries=[],datas=collect_data_files('soundcard'),hiddenimports=hidden,
           hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['tkinter','pytest','PySide6.QtDesigner','PySide6.QtQml','PySide6.QtQuick','numpy.tests'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Desk',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        disable_windowed_traceback=False,argv_emulation=False,version=str(base/'version-info.txt'),icon=[str(project/'assets/desk.ico')])
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Desk')
