import ipaddress

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from scripts.generate_dev_certificate import generate_certificate


def test_generate_dev_certificate_creates_localhost_certificate(tmp_path):
    cert_path, key_path = generate_certificate(tmp_path, days=30)
    certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
    private_key = serialization.load_pem_private_key(
        key_path.read_bytes(), password=None
    )
    subject_alt_names = certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value

    assert (
        certificate.public_key().public_numbers()
        == private_key.public_key().public_numbers()
    )
    assert (
        set(
            subject_alt_names.get_values_for_type(x509.DNSName)
        )
        == {"localhost"}
    )
    assert set(subject_alt_names.get_values_for_type(x509.IPAddress)) == {
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("::1"),
    }


def test_generate_dev_certificate_requires_force_to_replace(tmp_path):
    cert_path, key_path = generate_certificate(tmp_path)
    original_certificate = cert_path.read_bytes()

    with pytest.raises(FileExistsError, match="use --force"):
        generate_certificate(tmp_path)

    generate_certificate(tmp_path, force=True)
    assert cert_path.read_bytes() != original_certificate
    assert key_path.exists()
