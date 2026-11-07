"""Checks for the real-artifact installer integration harness."""

import importlib.util
import http.client
import os
from pathlib import Path
import ssl
import subprocess
from urllib.parse import urlsplit

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
    with harness.serve_local_https(tmp_path) as (base_url, ca_certificate):
        ca = x509.load_pem_x509_certificate(ca_certificate.read_bytes())
        assert ca.signature_hash_algorithm.name == "sha256"
        port = urlsplit(base_url).port
        assert port is not None
        context = ssl.create_default_context(cafile=str(ca_certificate))
        connection = http.client.HTTPSConnection("127.0.0.1", port, context=context)
        try:
            connection.request("GET", "/")
            assert connection.sock is not None
            server = x509.load_der_x509_certificate(
                connection.sock.getpeercert(binary_form=True)
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()
        assert server.signature_hash_algorithm.name == "sha256"


def test_native_installer_https_trust(harness, tmp_path):
    """Prove native curl/PowerShell trust before expensive frozen builds."""
    (tmp_path / "probe").write_text("verified TLS probe")
    with harness.serve_local_https(tmp_path) as (base_url, ca_certificate):
        url = f"{base_url}/probe"
        windows = os.name == "nt"
        script = tmp_path / ("probe.ps1" if windows else "probe.sh")
        script.write_text(
            f"param([string]$InstallDir)\nInvoke-RestMethod -Uri '{url}'\n"
            if windows
            else f"curl -fsS '{url}'\n"
        )
        environment = dict(os.environ, CURL_CA_BUNDLE=str(ca_certificate))
        command = harness.installer_command(
            script, tmp_path / "install", ca_certificate, None
        )
        assert "verified TLS probe" in harness.run(command, environment, timeout=60)


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
