import ipaddress
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from scripts import generate_dev_certificate
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
    constraints = certificate.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value
    usages = certificate.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage
    ).value

    assert constraints.ca is False
    assert ExtendedKeyUsageOID.SERVER_AUTH in usages


def test_generate_dev_certificate_requires_force_to_replace(tmp_path):
    cert_path, key_path = generate_certificate(tmp_path)
    original_certificate = cert_path.read_bytes()

    with pytest.raises(FileExistsError, match="use --force"):
        generate_certificate(tmp_path)

    generate_certificate(tmp_path, force=True)
    assert cert_path.read_bytes() != original_certificate
    assert key_path.exists()


def test_certificate_cli_reports_generated_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["generate_dev_certificate", "--output-dir", str(tmp_path)]
    )

    assert generate_dev_certificate.main() == 0

    output = capsys.readouterr().out
    assert f"Certificate: {tmp_path / 'localhost.pem'}" in output
    assert f"Private key: {tmp_path / 'localhost-key.pem'}" in output
    assert "local development only" in output


def test_certificate_cli_rejects_nonpositive_validity(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_dev_certificate", "--output-dir", str(tmp_path), "--days", "0"],
    )

    with pytest.raises(SystemExit) as error:
        generate_dev_certificate.main()

    assert error.value.code == 2
    assert "--days must be at least 1" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_certificate_cli_reports_output_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["generate_dev_certificate", "--output-dir", str(tmp_path)]
    )

    def fail_generation(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(generate_dev_certificate, "generate_certificate", fail_generation)

    assert generate_dev_certificate.main() == 1
    assert "Could not generate the development certificate: permission denied" in (
        capsys.readouterr().err
    )
