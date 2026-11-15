# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files,collect_submodules,collect_dynamic_libs
base=Path(SPECPATH);release=base.parent
sys.path.insert(0,str(release/'src'))
hidden=collect_submodules('novoacesso')+collect_submodules('metered_realtime')
hidden+=['soundcard','comtypes.client','comtypes.stream','comtypes.persist','dxcam','numpy','av','pypdfium2','pypdfium2_raw','PySide6.QtPrintSupport']
a=Analysis([str(release/'iniciar.py')],pathex=[str(release/'src')],binaries=collect_dynamic_libs('pypdfium2_raw'),
           datas=collect_data_files('soundcard')+collect_data_files('pypdfium2')+collect_data_files('pypdfium2_raw'),hiddenimports=hidden,hookspath=[],hooksconfig={},runtime_hooks=[],
           excludes=['tkinter','pytest','PySide6.QtDesigner','PySide6.QtQml','PySide6.QtQuick','numpy.tests'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Desk',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,disable_windowed_traceback=False,argv_emulation=False,
        version=str(base/'version-info.txt'),icon=[str(release/'assets/desk.ico')])
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Desk')
