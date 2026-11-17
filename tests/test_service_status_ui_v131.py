from PySide6.QtWidgets import QLineEdit
from novoacesso.app import MainWindow
from types import SimpleNamespace

def test_registration_refresh_is_read_only_and_names_the_running_version(monkeypatch):
    from novoacesso import service_client
    from novoacesso import __version__
    configured=[None];monkeypatch.setattr(service_client,'installed_configuration',lambda:configured[0])
    window=MainWindow()
    def forbidden():raise AssertionError('Reading registration must not authorize privileged control')
    monkeypatch.setattr('novoacesso.desktop.DesktopBackend',forbidden)
    try:
        window.refresh_service_registration()
        assert 'não instalado' in window.service_registration_status.text()
        assert __version__ in window.service_registration_status.text()
        configured[0]={'fixture':True};window.refresh_service_registration()
        assert 'registrado para este Desk' in window.service_registration_status.text()
        assert window.backend is None
    finally:window.quit_application()

def test_private_connection_profile_is_masked_without_changing_connect_payload():
    window=MainWindow()
    try:
        value='NAU1-synthetic-private-profile'
        window.remote_invite.setText(value)
        assert window.remote_invite.echoMode()==QLineEdit.EchoMode.Password
        assert window.remote_invite.text()==value
        window.remote_invite.setText('7369 0853 1099')
        assert window.remote_invite.echoMode()==QLineEdit.EchoMode.Normal
        assert window.remote_invite.text()=='7369 0853 1099'
    finally:window.quit_application()

def test_service_probe_requires_existing_host_lease_and_distinguishes_registration_from_response(monkeypatch):
    from novoacesso import service_client
    monkeypatch.setattr(service_client,'installed_configuration',lambda:{'fixture':True})
    calls=[];broker=SimpleNamespace(authorized=False,available=lambda:calls.append('probe') or True,input_state=lambda:(1,True),last_error_code=None)
    window=MainWindow();window.backend=SimpleNamespace(secure=broker,service_input_route=False)
    try:
        window.refresh_service_registration();assert not calls
        broker.authorized=True;window.refresh_service_registration()
        assert calls==['probe'] and 'Reconecte' in window.service_registration_status.text()
        window.backend.service_input_route=True;window.refresh_service_registration()
        assert 'Controle pelo serviço ativo' in window.service_registration_status.text()
        broker.available=lambda:False;broker.last_error_code=5;window.refresh_service_registration()
        assert 'não respondeu' in window.service_registration_status.text() and 'Código do Windows: 5' in window.service_registration_status.text()
    finally:window.backend=None;window.quit_application()
