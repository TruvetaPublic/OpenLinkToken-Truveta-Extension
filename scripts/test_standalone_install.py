"""Exercise real installers and extension updates against local HTTPS assets."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import functools
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
from urllib.request import urlopen
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from smoke_independent_extension_update import main as smoke_update
from openlinktoken_ext_truveta.util.extension_manifests import (
    create_extension_release_assets,
)


def run(
    command: list[str],
    environment: dict[str, str],
    *,
    fails: bool = False,
    timeout: int = 600,
) -> str:
    """Run a command, exposing its diagnostics and enforcing its exit status."""
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    print(f"$ {command}\n{result.stdout}\n{result.stderr}", flush=True)
    if (result.returncode != 0) != fails:
        raise RuntimeError(f"Unexpected exit code {result.returncode}: {command}")
    return result.stdout + result.stderr


def sha256(path: Path) -> str:
    """Return a file's SHA-256 using bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_tls(directory: Path) -> None:
    """Create an ephemeral CA and a localhost server certificate."""
    now = datetime.now(timezone.utc)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, directory.name)])
    ca = (
        x509.CertificateBuilder()
        .subject_name(issuer)
        .issuer_name(issuer)
        .public_key(issuer_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(issuer)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )
    ca_bytes = ca.public_bytes(serialization.Encoding.PEM)
    (directory / "ca.crt").write_bytes(ca_bytes)
    (directory / "server.crt").write_bytes(
        server.public_bytes(serialization.Encoding.PEM) + ca_bytes
    )
    (directory / "server.key").write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def stage_installer(source: Path, destination: Path, base: str) -> None:
    """Rewrite only the download endpoints in a temporary installer copy."""
    text = source.read_text(encoding="utf-8")
    for old, new in (
        ("https://github.com/${REPOSITORY}/releases", f"{base}/releases"),
        ("https://api.github.com/repos/${REPOSITORY}", f"{base}/api"),
        ("https://github.com/$Repository/releases", f"{base}/releases"),
        ("https://api.github.com/repos/$Repository", f"{base}/api"),
    ):
        text = text.replace(old, new)
    if text.count(base) != 2:
        raise RuntimeError(f"Installer endpoints changed: {source}")
    destination.write_text(text, encoding="utf-8")


def installer_command(
    script: Path, install: Path, ca: Path, version: str | None
) -> list[str]:
    """Build the platform installer invocation without disabling TLS checks."""
    if os.name != "nt":
        return [
            "bash",
            str(script),
            "--no-cuda",
            "--install-dir",
            str(install),
            *(["--version", version] if version else []),
        ]

    # PowerShell uses the Windows certificate store rather than SSL_CERT_FILE.
    def quote(path: Path | str) -> str:
        """Quote a literal PowerShell argument."""
        return "'" + str(path).replace("'", "''") + "'"

    command = (
        f"$cert = Import-Certificate -FilePath {quote(ca)} "
        "-CertStoreLocation Cert:\\LocalMachine\\Root; "
        "try { "
        f"& {quote(script)} -InstallDir {quote(install)} "
        + (f"-Version {quote(version)} " if version else "")
        + "} finally { Remove-Item -LiteralPath "
        "('Cert:\\LocalMachine\\Root\\' + $cert.Thumbprint) }"
    )
    return [
        "pwsh",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "$ErrorActionPreference = 'Stop'; " + command,
    ]


def exercise(args: argparse.Namespace, root: Path, base: str) -> None:
    """Install, reinstall and reject corrupt downloads, then run extension smoke."""
    environment = dict(
        os.environ,
        HOME=str(root / "home"),
        APPDATA=str(root / "home"),
        XDG_CONFIG_HOME=str(root / "home/.config"),
        OLT_EXTENSIONS_DIR=str(root / "home/extensions"),
        OLT_DISABLE_UPDATE_CHECK="1",
        SSL_CERT_FILE=str(root / "ca.crt"),
        CURL_CA_BUNDLE=str(root / "ca.crt"),
    )
    (root / "home").mkdir()
    serve = root / "serve"
    release = serve / "releases/download" / f"v{args.core_version}"
    release.mkdir(parents=True)
    asset = f"olt-cli-{args.core_version}-{args.target}.zip"
    archive = release / asset
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for path in sorted(args.cli.parent.rglob("*")):
            relative = path.relative_to(args.cli.parent)
            if path.is_file() and relative.parts[:2] != ("_internal", "nvidia"):
                output.write(path, Path("olt") / relative)
    checksum = release / f"{asset}.sha256"
    checksum.write_text(f"{sha256(archive)}  {asset}\n", encoding="utf-8")
    latest = serve / "api/releases/latest"
    latest.parent.mkdir(parents=True)
    latest.write_text(json.dumps({"tag_name": f"v{args.core_version}"}, indent=2))
    suffix = "ps1" if os.name == "nt" else "sh"
    staged_script = serve / f"install.{suffix}"
    stage_installer(args.core / f"install.{suffix}", staged_script, base)
    downloaded = root / f"downloaded-install.{suffix}"
    with urlopen(
        f"{base}/{staged_script.name}",
        context=ssl.create_default_context(cafile=str(root / "ca.crt")),
        timeout=30,
    ) as response:
        downloaded.write_bytes(response.read())
    if downloaded.read_bytes() != staged_script.read_bytes():
        raise RuntimeError("Downloaded installer differs from served installer")
    install = root / "install with spaces"
    cli = install / ("olt.exe" if os.name == "nt" else "olt")
    ca = root / "ca.crt"
    run(installer_command(downloaded, install, ca, None), environment)
    if args.core_version not in run([str(cli), "--version"], environment):
        raise RuntimeError("Installed CLI has the wrong version")
    before = sha256(cli)
    saved = checksum.read_bytes()
    checksum.write_text(f"{'0' * 64}  {asset}\n", encoding="utf-8")
    try:
        output = run(
            installer_command(downloaded, install, ca, args.core_version),
            environment,
            fails=True,
        )
        if "SHA-256 verification failed" not in output or sha256(cli) != before:
            raise RuntimeError("Corrupt download was not rejected safely")
    finally:
        checksum.write_bytes(saved)
    run(installer_command(downloaded, install, ca, args.core_version), environment)
    if sha256(cli) != before:
        raise RuntimeError("Reinstallation changed the CLI executable")
    run(
        [str(cli), "generate-key-pair", "--name", "ci-recipient", "--force"],
        environment,
    )
    bundles = sorted(args.bundles.glob("*.zip"))
    for path in bundles:
        shutil.copyfile(path, serve / path.name)
    create_extension_release_assets(args.extension_version, args.wheel, bundles, serve)
    for name in (
        "openlinktoken-ext-truveta-bootstrap.json",
        "openlinktoken-ext-truveta-update.json",
    ):
        path = serve / name
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for bundle in manifest["bundles"]:
            bundle["url"] = base + "/" + bundle["url"].rsplit("/", 1)[1]
        if isinstance(manifest["extension"], dict):
            manifest["extension"]["update_manifest_url"] = (
                base + "/openlinktoken-ext-truveta-update.json"
            )
        path.write_text(json.dumps(manifest), encoding="utf-8")
    bootstrap = serve / "openlinktoken-ext-truveta-bootstrap.json"
    original = bootstrap.read_bytes()
    for failure in ("checksum", "abi"):
        manifest = json.loads(original)
        if failure == "checksum":
            for bundle in manifest["bundles"]:
                bundle["sha256"] = "0" * 64
            expected = "Bundle checksum verification failed"
        else:
            manifest["bundles"] = [
                bundle
                for bundle in manifest["bundles"]
                if bundle["python_abi"] != args.python_abi
            ]
            expected = "No extension bundle is available"
        bootstrap.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            output = run(
                [
                    str(cli),
                    "extension",
                    "install",
                    "--yes",
                    "--manifest",
                    base + "/" + bootstrap.name,
                ],
                environment,
                fails=True,
            )
            registry = root / "home/extensions/registry.json"
            if expected not in output or (
                registry.exists() and "truveta" in json.loads(registry.read_text())
            ):
                raise RuntimeError(
                    f"Invalid extension {failure} was not rejected safely"
                )
        finally:
            bootstrap.write_bytes(original)
    os.environ["SSL_CERT_FILE"] = str(ca)
    smoke_update(
        [
            "--fresh-core",
            "--cli",
            str(cli),
            "--target",
            args.target,
            "--python-abi",
            args.python_abi,
            "--manifest-url",
            base + "/openlinktoken-ext-truveta-bootstrap.json",
        ]
    )
    print(f"PASS: installer + extension lifecycle: {args.target}/{args.python_abi}")


def main() -> None:
    """Run the isolated, real-artifact HTTPS integration check."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("core", "cli", "wheel", "bundles"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("core-version", "extension-version", "target", "python-abi"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    for name in ("core", "cli", "wheel", "bundles"):
        setattr(args, name, getattr(args, name).resolve())
    with tempfile.TemporaryDirectory(prefix="olt-integration-") as directory:
        root = Path(directory)
        (root / "serve").mkdir()
        prepare_tls(root)
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(root / "server.crt", root / "server.key")
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(root / "serve")
        )
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                exercise(args, root, f"https://127.0.0.1:{server.server_port}")
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    main()
