"""Início automático opcional, visível na bandeja, após login do usuário Windows."""
import os,sys

def set_autostart(enabled):
    if os.name!='nt':raise RuntimeError('Início automático disponível neste pacote somente no Windows.')
    if enabled and not getattr(sys,'frozen',False):raise RuntimeError('Configure o início automático usando o executável compilado.')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'NovoAcesso',0,winreg.REG_SZ,'"'+sys.executable+'" --background')
        else:
            try:winreg.DeleteValue(key,'NovoAcesso')
            except FileNotFoundError:pass
