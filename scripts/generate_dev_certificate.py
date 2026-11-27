"""Generate a self-signed TLS certificate for local development."""

import argparse
import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "certs"


def generate_certificate(
    output_dir: Path, days: int = 365, force: bool = False
) -> tuple[Path, Path]:
    """Create a localhost certificate and its private key in ``output_dir``."""
    cert_path = output_dir / "localhost.pem"
    key_path = output_dir / "localhost-key.pem"
    if not force and (cert_path.exists() or key_path.exists()):
        raise FileExistsError(
            f"Certificate files already exist in {output_dir}; "
            "use --force to replace them."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    if os.name == "posix":
        key_path.chmod(0o600)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "directory for the certificate and private key "
            f"(default: {DEFAULT_OUTPUT_DIR})"
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="certificate validity in days (default: 365)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing certificate files",
    )
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")

    try:
        cert_path, key_path = generate_certificate(
            args.output_dir, args.days, args.force
        )
    except OSError as exc:
        print(
            f"Could not generate the development certificate: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Certificate: {cert_path}")
    print(f"Private key: {key_path}")
    print("This self-signed certificate is for local development only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
