"""Início automático opcional, visível na bandeja, após login do usuário Windows."""
import os,sys

def set_autostart(enabled):
    from .package_support import is_packaged
    if is_packaged():raise RuntimeError('Gerencie o início do Desk nas configurações Inicializar do Windows.')
    if os.name!='nt':raise RuntimeError('Início automático disponível neste pacote somente no Windows.')
    if enabled and not getattr(sys,'frozen',False):raise RuntimeError('Configure o início automático usando o executável compilado.')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'NovoAcesso',0,winreg.REG_SZ,'"'+sys.executable+'" --background')
        else:
            try:winreg.DeleteValue(key,'NovoAcesso')
            except FileNotFoundError:pass
