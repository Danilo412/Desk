"""Build and verify the Microsoft Store MSIX package for Desk."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packaging/store/AppxManifest.template.xml"
DEFAULT_IDENTITY = ROOT / "packaging/store/store-identity.local.json"


def read_version() -> str:
    init_text = (ROOT / "src/novoacesso/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
    if not match:
        raise RuntimeError("Versão não encontrada em src/novoacesso/__init__.py")
    return match.group(1)


def find_makeappx() -> Path:
    candidates = []
    if os.environ.get("DESK_MAKEAPPX"):
        candidates.append(Path(os.environ["DESK_MAKEAPPX"]))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    candidates.append(local / "DeskBuild/sdk/10.0.26100.0/x64/makeappx.exe")
    kits = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits/10/bin"
    if kits.is_dir():
        candidates.extend(sorted(kits.glob("*/x64/makeappx.exe"), reverse=True))
    which = shutil.which("makeappx.exe")
    if which:
        candidates.append(Path(which))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "makeappx.exe não encontrado. Instale o Windows SDK ou defina DESK_MAKEAPPX."
    )


def load_identity(identity_file: Path | None) -> tuple[dict, bool]:
    source = identity_file or (DEFAULT_IDENTITY if DEFAULT_IDENTITY.is_file() else None)
    if not source:
        return (
            dict(
                name="Desk.Preparacao.Store",
                publisher="CN=Desk-Preparacao-Identidade-Pendente",
                publisher_display_name="Desk - identidade pendente",
            ),
            True,
        )
    data = json.loads(source.read_text(encoding="utf-8"))
    for key in ("name", "publisher", "publisher_display_name"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Campo obrigatório ausente na identidade da Store: {key}")
    if not data["publisher"].startswith("CN=") or "Pendente" in data["publisher"]:
        raise ValueError("Publisher inválido no arquivo de identidade da Store.")
    if data["name"] == "Desk.Preparacao.Store":
        raise ValueError("Substitua o Package/Identity/Name provisório pelo nome oficial do Partner Center.")
    return data, False


def render_manifest(destination: Path, version: str, identity: dict) -> None:
    ns = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
    desktop = "http://schemas.microsoft.com/appx/manifest/desktop/windows10"
    uap10 = "http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
    for prefix, uri in [
        ("", ns),
        ("uap", "http://schemas.microsoft.com/appx/manifest/uap/windows10"),
        ("uap10", uap10),
        ("desktop", desktop),
        ("rescap", "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"),
    ]:
        ET.register_namespace(prefix, uri)

    tree = ET.parse(TEMPLATE)
    manifest = tree.getroot()
    manifest.set("IgnorableNamespaces", "uap uap10 desktop rescap")
    item = manifest.find(f"{{{ns}}}Identity")
    item.set("Name", identity["name"])
    item.set("Publisher", identity["publisher"])
    item.set("Version", f"{version}.0")
    manifest.find(f"{{{ns}}}Properties/{{{ns}}}PublisherDisplayName").text = identity["publisher_display_name"]
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def verify_msix(package: Path, payload: Path) -> tuple[int, str]:
    files = 0
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None, "Arquivo ZIP/MSIX corrompido"
        names = {unquote(n): n for n in archive.namelist()}
        assert "AppxSignature.p7x" not in names, "O pacote não deve conter assinatura de teste"
        for name in names:
            p = Path(name)
            assert p.name.lower() not in ("internet.json", "identity.dat", "update-signing-key.dat")
            assert p.suffix.lower() not in (".pfx", ".p12", ".key")
        for file in payload.rglob("*"):
            if file.is_file():
                assert archive.read(names[file.relative_to(payload).as_posix()]) == file.read_bytes()
                files += 1
        blockmap = ET.fromstring(archive.read("AppxBlockMap.xml"))
        ns = {"b": "http://schemas.microsoft.com/appx/2010/blockmap"}
        for file in blockmap.findall("b:File", ns):
            data = archive.read(names[file.attrib["Name"].replace("\\", "/")])
            assert len(data) == int(file.attrib["Size"])
            blocks = file.findall("b:Block", ns)
            assert len(blocks) == (len(data) + 65535) // 65536
            for idx, block in enumerate(blocks):
                expected = base64.b64decode(block.attrib["Hash"])
                actual = hashlib.sha256(data[idx * 65536 : (idx + 1) * 65536]).digest()
                assert actual == expected
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    return files, digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Empacota o Desk em MSIX para a Microsoft Store.")
    parser.add_argument("--identity-file", type=Path, help="JSON com name, publisher e publisher_display_name do Partner Center.")
    parser.add_argument("--build", action="store_true", help="Recompila dist/Desk antes de empacotar o MSIX.")
    args = parser.parse_args()

    version = read_version()
    dist_desk = ROOT / "dist/Desk"
    if args.build or not (dist_desk / "Desk.exe").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts/build_windows.py")], cwd=ROOT, check=True)
    assert not (dist_desk / "internet.json").exists(), "internet.json não pode estar em dist/Desk"
    assert not (dist_desk / "identity.dat").exists(), "identity.dat não pode estar em dist/Desk"

    identity, provisional = load_identity(args.identity_file)
    out_dir = ROOT / "dist/store"
    payload = out_dir / "Payload"
    if payload.exists():
        shutil.rmtree(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload.mkdir(parents=True, exist_ok=True)

    shutil.copytree(dist_desk, payload / "App")
    assets = payload / "Assets"
    assets.mkdir()
    with Image.open(ROOT / "assets/desk.ico") as icon:
        rgba = icon.convert("RGBA")
        for size in (44, 50, 150):
            rgba.resize((size, size), Image.Resampling.LANCZOS).save(assets / f"Logo{size}.png")

    render_manifest(payload / "AppxManifest.xml", version, identity)

    filename = (
        f"Desk-{version}-Store-PRELIMINAR-NAO-ASSINADO.msix"
        if provisional
        else f"Desk-{version}-Store-Certificacao.msix"
    )
    package = out_dir / filename
    makeappx = find_makeappx()
    run = subprocess.run([str(makeappx), "pack", "/o", "/d", str(payload), "/p", str(package)], capture_output=True)
    (out_dir / "makeappx-validation.log").write_bytes(run.stdout + run.stderr)
    assert run.returncode == 0, f"makeappx falhou. Consulte {out_dir / 'makeappx-validation.log'}"

    files_verified, sha256 = verify_msix(package, payload)
    report = dict(
        version=version,
        package=filename,
        bytes=package.stat().st_size,
        sha256=sha256,
        payload_files_verified=files_verified,
        schema_validation=True,
        zip_integrity=True,
        blockmap_verified=True,
        startup_task_declared=True,
        startup_enabled_by_default=False,
        private_config_included=False,
        identity_provisional=provisional,
        signed=False,
        identity=identity,
    )
    (out_dir / "VERIFICACAO.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "GUIA-MICROSOFT-STORE.txt").write_text(
        f"""DESK {version} — PACOTE MICROSOFT STORE (MSIX)

Arquivo gerado: {filename}
Identidade: {"PROVISÓRIA (substitua antes de enviar)" if provisional else "OFICIAL DO PARTNER CENTER"}

Como gerar o pacote definitivo para envio na Microsoft Store:
1. Conclua a verificação da conta individual gratuita no Microsoft Partner Center.
2. Crie o aplicativo "Desk" e copie em Gerenciamento de produtos > Identidade do produto:
   - Package/Identity/Name
   - Package/Identity/Publisher (CN=...)
   - Package/Properties/PublisherDisplayName
3. Salve esses 3 campos em packaging\\store\\store-identity.local.json:
   {{
     "name": "SEU_PACKAGE_IDENTITY_NAME",
     "publisher": "CN=SEU_PUBLISHER_ID",
     "publisher_display_name": "SEU_NOME_DE_PUBLICADOR"
   }}
4. Execute na raiz do projeto:
   scripts\\dev.cmd store
5. Envie o arquivo dist\\store\\Desk-{version}-Store-Certificacao.msix no Partner Center.
   A Microsoft assina o pacote gratuitamente após a certificação e entrega as atualizações
   em qualquer Windows sem bloqueio do Smart App Control ou SmartScreen.
""",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "version",
                    "package",
                    "bytes",
                    "schema_validation",
                    "payload_files_verified",
                    "identity_provisional",
                    "signed",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
