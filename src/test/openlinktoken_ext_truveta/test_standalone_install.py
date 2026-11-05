"""Checks for the real-artifact installer integration harness."""

import importlib.util
import functools
import http.server
import os
from pathlib import Path
import ssl
import subprocess
import threading

import pytest
from cryptography import x509


@pytest.fixture
def harness(monkeypatch):
    """Load the integration harness with its sibling smoke module."""
    scripts = Path(__file__).parents[3] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "installer_harness", scripts / "test_standalone_install.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("suffix", ["sh", "ps1"])
def test_stages_real_installer_endpoints_only(harness, tmp_path, suffix):
    """Local testing must not replace installer logic or disable TLS."""
    # Use endpoint fixtures so this suite does not require the other checkout.
    endpoints = (
        ("${REPOSITORY}", "readonly ") if suffix == "sh" else ("$Repository", "")
    )
    repository, prefix = endpoints
    original = (
        f'{prefix}RELEASES="https://github.com/{repository}/releases"\n'
        f'{prefix}API="https://api.github.com/repos/{repository}"\n'
        "unchanged installer logic\n"
    )
    source = tmp_path / f"install.{suffix}"
    source.write_text(original)
    output = tmp_path / "downloaded"
    harness.stage_installer(source, output, "https://127.0.0.1:1234")
    assert output.read_text().count("https://127.0.0.1:1234") == 2
    assert output.read_text().endswith("unchanged installer logic\n")


def test_endpoint_drift_fails_explicitly(harness, tmp_path):
    """A changed installer must not accidentally fall back to GitHub."""
    source = tmp_path / "install.sh"
    source.write_text("changed endpoints")
    with pytest.raises(RuntimeError, match="Installer endpoints changed"):
        harness.stage_installer(source, tmp_path / "out", "https://127.0.0.1:1")


def test_tls_certificates_use_sha256(harness, tmp_path):
    """Generate an explicit chain without platform OpenSSL configuration."""
    harness.prepare_tls(tmp_path)
    for name in ("ca.crt", "server.crt"):
        certificate = x509.load_pem_x509_certificate((tmp_path / name).read_bytes())
        assert certificate.signature_hash_algorithm.name == "sha256"


def test_native_installer_https_trust(harness, tmp_path):
    """Prove native curl/PowerShell trust before expensive frozen builds."""
    harness.prepare_tls(tmp_path)
    (tmp_path / "probe").write_text("verified TLS probe")
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = f"https://127.0.0.1:{server.server_port}/probe"
            windows = os.name == "nt"
            script = tmp_path / ("probe.ps1" if windows else "probe.sh")
            script.write_text(
                f"param([string]$InstallDir)\nInvoke-RestMethod -Uri '{url}'\n"
                if windows
                else f"curl -fsS '{url}'\n"
            )
            environment = dict(os.environ, CURL_CA_BUNDLE=str(tmp_path / "ca.crt"))
            command = harness.installer_command(
                script, tmp_path / "install", tmp_path / "ca.crt", None
            )
            assert "verified TLS probe" in harness.run(command, environment, timeout=60)
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.parametrize("code,fails", [(0, True), (1, False)])
def test_unexpected_command_status_fails(harness, monkeypatch, code, fails):
    """A negative check cannot pass merely because its subprocess ran."""
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, code, "", ""),
    )
    with pytest.raises(RuntimeError, match="Unexpected exit code"):
        harness.run(["fake"], {}, fails=fails)
