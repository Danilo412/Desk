"""Read-only package payload, private per-user configuration and Windows startup UI."""
import ctypes
import json
import os
from pathlib import Path
import sys


def is_packaged():
    if os.name != 'nt':
        return False
    length = ctypes.c_uint32()
    try:
        query = ctypes.WinDLL('kernel32', use_last_error=True).GetCurrentPackageFullName
        query.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
        query.restype = ctypes.c_long
        return query(ctypes.byref(length), None) == 122 and length.value > 0
    except (AttributeError, OSError):
        return False


def internet_config_path(app_file=None):
    state = Path(
        os.environ.get('NOVOACESSO_STATE_DIR')
        or Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'NovoAcesso'
    )
    user_config = state / 'internet.json'
    if is_packaged() or user_config.is_file():
        return user_config
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'internet.json'
    return Path(app_file or __file__).resolve().parents[2] / 'internet.json'


def import_relay_token(path):
    """Import only transport settings; never device identity or authorization state."""
    from .relay import token_encode, validate_endpoint
    path = Path(path)
    if path.stat().st_size > 256 * 1024:
        raise ValueError('Configuration too large')
    with path.open('rb') as stream:
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError('Configuration too large')
    config = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(config, dict):
        raise ValueError('Invalid configuration')
    endpoint = validate_endpoint(dict(mode='metered', api_key=config['public_key'], ice_servers=config['ice_servers']))
    return token_encode('NAR1-', endpoint)


def open_startup_settings():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    if not QDesktopServices.openUrl(QUrl('ms-settings:startupapps')):
        raise RuntimeError('Abra Configurações do Windows > Aplicativos > Inicializar para gerenciar o Desk.')
