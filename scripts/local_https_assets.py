"""Serve local release assets over a trusted loopback HTTPS endpoint."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import functools
import http.server
import ipaddress
import ssl
import tempfile
import threading
from pathlib import Path
from typing import Iterator

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@contextmanager
def serve_local_https(directory: Path) -> Iterator[tuple[str, Path]]:
    """Serve a directory on loopback HTTPS with a temporary trusted certificate.

    Args:
        directory: Existing directory whose files should be served.

    Yields:
        The HTTPS base URL and path to the temporary CA certificate.
    """
    if not directory.is_dir():
        raise NotADirectoryError(f"Asset directory does not exist: {directory}")

    with tempfile.TemporaryDirectory(prefix="olt-local-https-") as certificate_dir:
        certificates = Path(certificate_dir)
        _prepare_tls(certificates)

        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            certificates / "server.crt", certificates / "server.key"
        )
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(directory)
        )
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                yield (
                    f"https://127.0.0.1:{server.server_port}",
                    certificates / "ca.crt",
                )
            finally:
                server.shutdown()
                thread.join()


def _prepare_tls(directory: Path) -> None:
    """Create an ephemeral CA and a localhost server certificate.

    Args:
        directory: Directory where the CA, server certificate, and key are written.

    Returns:
        None.
    """
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
