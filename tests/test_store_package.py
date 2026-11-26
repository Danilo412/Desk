import json
from pathlib import Path
import pytest
from novoacesso import package_support as package
from novoacesso.relay import endpoint_from_token


def test_store_config_uses_private_user_folder(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(package, 'is_packaged', lambda: True)
    assert package.internet_config_path() == tmp_path / 'internet.json'
    assert not (tmp_path / 'internet.json').exists()


def test_existing_private_config_precedes_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(package, 'is_packaged', lambda: False)
    (tmp_path / 'internet.json').write_text('{}')
    assert package.internet_config_path() == tmp_path / 'internet.json'


def test_unpacked_without_user_config_retains_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVOACESSO_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(package, 'is_packaged', lambda: False)
    monkeypatch.setattr(package.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(package.sys, 'executable', str(tmp_path / 'App' / 'Desk.exe'))
    assert package.internet_config_path() == tmp_path / 'App' / 'internet.json'


def test_relay_import_never_imports_trusted_devices_or_local_identity(tmp_path):
    path = tmp_path / 'relay.json'
    path.write_text(json.dumps(dict(
        public_key='pk_live_' + 'a' * 32,
        ice_servers=[dict(urls=['turn:free.expressturn.com:3478?transport=udp'], username='test-user', credential='test-password')],
        trusted_devices=['malicious-device'],
        identity='malicious-identity',
        unattended=True,
    )))
    token = package.import_relay_token(path)
    endpoint = endpoint_from_token(token)
    assert endpoint['mode'] == 'metered'
    assert endpoint['ice_servers'][0]['credential'] == 'test-password'
    assert not {'trusted_devices', 'identity', 'unattended'} & endpoint.keys()


@pytest.mark.parametrize('value', ['not json', '[]', '{}', 'null'])
def test_reject_invalid_import_without_exposing_file_contents(tmp_path, value):
    path = tmp_path / 'bad.json'
    path.write_text(value)
    with pytest.raises((ValueError, KeyError, TypeError)):
        package.import_relay_token(path)


def test_reject_large_config(tmp_path):
    path = tmp_path / 'oversized.json'
    path.write_bytes(b' ' * (256 * 1024 + 1))
    with pytest.raises(ValueError, match='too large'):
        package.import_relay_token(path)


def test_store_startup_is_managed_by_windows_not_registry(monkeypatch):
    from novoacesso import startup
    monkeypatch.setattr(package, 'is_packaged', lambda: True)
    with pytest.raises(RuntimeError, match='Windows'):
        startup.set_autostart(True)


def test_store_ui_provides_windows_startup_action_without_claiming_enabled(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from novoacesso.app import MainWindow
    monkeypatch.setenv('NOVOACESSO_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(package, 'is_packaged', lambda: True)
    window = MainWindow()
    try:
        assert not window.autostart.isEnabled()
        assert not window.auto_download_updates.isEnabled()
        assert not window.auto_install_on_exit.isEnabled()
        assert any(b.text() == 'Gerenciar início com o Windows' for b in window.findChildren(QPushButton))
        assert any(b.text() == 'Importar configuração de conexão…' for b in window.findChildren(QPushButton))
    finally:
        window.close()


def test_import_ui_saves_transport_and_restores_numeric_service_without_bundled_credentials(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QPushButton
    from novoacesso.app import MainWindow
    monkeypatch.setenv('NOVOACESSO_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('NOVOACESSO_OFFLINE', '0')
    monkeypatch.setenv('DESK_AUTOREADY', '0')
    monkeypatch.setattr(MainWindow, 'prepare_address', lambda self: None)
    monkeypatch.setattr(package, 'is_packaged', lambda: True)
    path = tmp_path / 'relay.json'
    key = 'pk_live_' + 'b' * 32
    path.write_text(json.dumps(dict(
        public_key=key,
        ice_servers=[dict(urls=['turn:free.expressturn.com:3478?transport=udp'], username='test-user', credential='test-password')],
    )))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(path), ''))
    window = MainWindow()
    try:
        number = window.identity.desk_address
        assert not window.cloud_signaling_key
        button = next(b for b in window.findChildren(QPushButton) if b.text() == 'Importar configuração de conexão…')
        button.click()
        assert window.cloud_signaling_key == key
        assert window.identity.settings()['use_relay']
        assert window.relay_endpoint()['api_key'] == key
        assert window.identity.desk_address == number
    finally:
        window.close()
    reopened = MainWindow()
    try:
        assert reopened.cloud_signaling_key == key
        assert reopened.relay_endpoint()['api_key'] == key
        assert reopened.identity.desk_address == number
        assert not reopened.identity.settings().get('unattended')
    finally:
        reopened.close()
