"""Build, sign, verify and optionally publish a Desk Windows release."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = "Danilo412/Desk"
DEFAULT_NOTES = (
    "Novo visual profissional Astryx, correções de interface e atualizações automáticas "
    "em segundo plano com conferência Ed25519 e SHA-256. Encerre sessões e gravações "
    "antes de instalar. Atualiza somente o aplicativo. O instalador está sem assinatura Authenticode."
)


def read_version() -> str:
    init_text = (ROOT / "src/novoacesso/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
    if not match:
        raise RuntimeError("Não foi possível ler __version__ em src/novoacesso/__init__.py")
    return match.group(1)


def run(*args, cwd=ROOT, env=None, timeout=600) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return result.stdout.strip()


def run_stream(*args, cwd=ROOT, env=None, timeout=900) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=timeout)


def gh_api(path: str):
    return json.loads(run("gh", "api", path, "-H", "Cache-Control: no-cache", timeout=60))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def audit_clean_build(dist_desk: Path, dist_publish: Path) -> None:
    forbidden = {"internet.json", "identity.dat", "update-signing-key.dat"}
    for folder in (dist_desk, dist_publish):
        leaks = [str(p) for p in folder.rglob("*") if p.is_file() and p.name in forbidden]
        if leaks:
            raise RuntimeError(f"Arquivos privados detectados no pacote público: {leaks}")


def sign_manifest(version: str, setup_path: Path, publish_dir: Path, notes: str) -> Path:
    sys.path.insert(0, str(ROOT / "src"))
    from novoacesso.identity import protect
    from novoacesso import updater
    from novoacesso.update_trust import UPDATE_PUBLIC_KEY
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    tag = f"v{version}"
    payload = dict(
        schema=1,
        version=version,
        platform="windows-x64",
        url=f"https://github.com/{REPO}/releases/download/{tag}/{setup_path.name}",
        sha256=sha256(setup_path),
        size=setup_path.stat().st_size,
        notes=notes,
    )
    private_path = Path(os.environ["LOCALAPPDATA"]) / "DeskPublisher/update-signing-key.dat"
    if not private_path.is_file():
        raise FileNotFoundError(f"Chave do publicador não encontrada em {private_path}")
    key = Ed25519PrivateKey.from_private_bytes(protect(private_path.read_bytes(), False))
    try:
        pub_hex = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        assert pub_hex == UPDATE_PUBLIC_KEY, "Chave privada não corresponde a UPDATE_PUBLIC_KEY"
        signature = base64.b64encode(key.sign(updater.canonical(payload))).decode("ascii")
    finally:
        del key

    manifest = publish_dir / "desk-update.json"
    manifest.write_text(
        json.dumps(dict(payload=payload, signature=signature), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for installed in ("0.12.0", "0.14.2", "0.14.4"):
        if updater.version_tuple(installed) < updater.version_tuple(version):
            offer = updater.verify_manifest(manifest.read_bytes(), installed)
            assert offer and offer.version == version and offer.sha256 == payload["sha256"]
    assert updater.verify_manifest(manifest.read_bytes(), version) is None
    return manifest


def write_checksums(publish_dir: Path, files: list[Path]) -> Path:
    sums = publish_dir / "SHA256SUMS.txt"
    sums.write_text(
        "".join(f"{sha256(f)}  {f.name}\n" for f in files),
        encoding="ascii",
    )
    return sums


def release_by_tag(tag: str):
    for _ in range(6):
        releases = gh_api(f"repos/{REPO}/releases?per_page=50&desk_check={time.time_ns()}")
        found = next((r for r in releases if r["tag_name"] == tag), None)
        if found is not None:
            return found
        try:
            view = json.loads(run("gh", "release", "view", tag, "--repo", REPO, "--json", "databaseId,tagName,isDraft"))
            return gh_api(f"repos/{REPO}/releases/{view['databaseId']}")
        except subprocess.CalledProcessError:
            time.sleep(1.5)
    return None


def verify_assets(tag: str, release: dict, files: list[Path]) -> None:
    expected = {f.name: f for f in files}
    assert {a["name"] for a in release["assets"]} == expected.keys(), "Lista de assets difere"
    for asset in release["assets"]:
        local = expected[asset["name"]]
        assert asset["size"] == local.stat().st_size, f"Tamanho divergente: {asset['name']}"
        if asset.get("digest"):
            assert asset["digest"] == "sha256:" + sha256(local), f"SHA divergente: {asset['name']}"


def verify_public_channel(version: str, setup_path: Path, tag: str) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from novoacesso import updater

    expected_sha = sha256(setup_path)
    expected_size = setup_path.stat().st_size
    error = None
    offer = None
    release = None
    for _ in range(10):
        try:
            release = gh_api(f"repos/{REPO}/releases/latest")
            offer = updater.check_update("0.14.4")
            assert release["tag_name"] == tag and not release["draft"] and not release["prerelease"]
            assert offer and offer.version == version
            assert offer.size == expected_size and offer.sha256 == expected_sha
            break
        except (AssertionError, updater.UpdateError) as exc:
            error = exc
            time.sleep(3)
    else:
        raise RuntimeError("Falha ao validar canal público após publicar") from error

    with tempfile.TemporaryDirectory(prefix="desk-verify-public-") as tmp:
        downloaded = updater.download_update(offer, Path(tmp))
        assert sha256(downloaded) == expected_sha
        if os.name == "nt":
            zone = Path(str(downloaded) + ":Zone.Identifier").read_text(encoding="utf-8")
            assert "ZoneId=3" in zone

    return dict(
        version=version,
        release=release["html_url"],
        public_download_verified=True,
        installer_size=expected_size,
        installer_sha256=expected_sha,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compila, assina e publica uma versão do Desk.")
    parser.add_argument("--publish", action="store_true", help="Faz push da main e publica a GitHub Release como Latest.")
    parser.add_argument("--skip-tests", action="store_true", help="Pula a suíte pytest (use apenas após já ter rodado os testes).")
    parser.add_argument("--dry-run", action="store_true", help="Executa build e validação local sem enviar ao GitHub.")
    parser.add_argument("--notes", default=DEFAULT_NOTES, help="Notas curtas exibidas no diálogo de atualização.")
    args = parser.parse_args()

    version = read_version()
    tag = f"v{version}"
    dist_desk = ROOT / "dist/Desk"
    dist_publish = ROOT / "dist/publish"
    py = sys.executable

    test_env = os.environ.copy()
    test_env.update(
        QT_QPA_PLATFORM="offscreen",
        NOVOACESSO_OFFLINE="1",
        DESK_AUTOREADY="0",
        PYTHONPATH=str(ROOT / "src"),
    )

    if args.publish and not args.dry_run:
        dirty = run("git", "status", "--porcelain")
        if dirty:
            raise RuntimeError(f"Worktree possui alterações não commitadas:\n{dirty}")

    if not args.skip_tests:
        print(f"[1/6] Executando testes para Desk {version}…")
        run_stream(py, "-m", "pytest", "tests", "-q", "--disable-warnings", env=test_env)
    else:
        print("[1/6] Testes ignorados por --skip-tests.")

    print("[2/6] Compilando aplicativo público (build_windows.py)…")
    run_stream(py, str(ROOT / "scripts/build_windows.py"))

    print("[3/6] Validando pacote compilado (validate_package.py)…")
    val = subprocess.run(
        [py, str(ROOT / "scripts/validate_package.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if val.returncode == 0:
        if val.stdout.strip():
            print(val.stdout.strip())
    elif "4551" in (val.stdout + val.stderr):
        print(
            "[aviso] validate_package.py bloqueado pelo Controle de Aplicativo do Windows (WinError 4551) "
            "para binário local sem Authenticode. Executando auditoria estática do pacote; "
            "a validação em execução continua sendo executada no GitHub Actions."
        )
        for rel_path in ("Desk.exe", "COMO-USAR.txt", "LICENSE", "internet.example.json"):
            assert (dist_desk / rel_path).is_file(), f"Ausente em dist/Desk: {rel_path}"
        assert (dist_desk / "assets").is_dir() and (dist_desk / "licencas").is_dir()
    else:
        print(val.stdout)
        print(val.stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(val.returncode, val.args, val.stdout, val.stderr)

    print("[4/6] Compilando instalador Inno Setup (build_installer.py)…")
    run_stream(py, str(ROOT / "scripts/build_installer.py"))
    audit_clean_build(dist_desk, dist_publish)

    setup_path = dist_publish / f"Desk-{version}-Update.exe"
    source_path = dist_publish / f"Desk-{version}-Codigo-Fonte.zip"
    assert setup_path.is_file() and source_path.is_file()

    print("[5/6] Assinando manifesto desk-update.json com Ed25519…")
    manifest_path = sign_manifest(version, setup_path, dist_publish, args.notes)
    assets = [setup_path, source_path, manifest_path]
    sums_path = write_checksums(dist_publish, assets)
    all_files = assets + [sums_path]

    if not args.publish or args.dry_run:
        report = dict(
            version=version,
            published=False,
            dry_run=args.dry_run,
            artifacts=[str(p) for p in all_files],
            installer_sha256=sha256(setup_path),
            installer_size=setup_path.stat().st_size,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("[6/6] Publicando no GitHub e validando canal público…")
    assert gh_api("user")["login"] == "Danilo412"
    assert run("git", "remote", "get-url", "origin") == f"https://github.com/{REPO}.git"
    commit = run("git", "rev-parse", "HEAD")
    run_stream("git", "push", "origin", "main")

    notes_file = dist_publish / "release-notes.txt"
    notes_file.write_text(
        f"## Desk {version}\n\n{args.notes}\n\n"
        "## Como atualizar\n\n"
        "O Desk verifica e baixa atualizações automaticamente em segundo plano.\n"
        "Quando estiver pronta, clique em **Instalar agora** no aviso da tela inicial ou em **Atualizações**.\n",
        encoding="utf-8",
    )

    rel = release_by_tag(tag)
    if rel is None:
        run(
            "gh", "release", "create", tag,
            "--repo", REPO, "--draft", "--target", commit,
            "--title", f"Desk {version}",
            "--notes-file", str(notes_file),
            timeout=90,
        )
        rel = release_by_tag(tag)

    run("gh", "release", "upload", tag, "--repo", REPO, "--clobber", *[str(f) for f in all_files], timeout=240)

    rel = gh_api(f"repos/{REPO}/releases/{rel['id']}")
    verify_assets(tag, rel, all_files)
    run("gh", "release", "edit", tag, "--repo", REPO, "--draft=false", "--latest", timeout=60)
    report = verify_public_channel(version, setup_path, tag)
    (dist_publish / "publication.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
