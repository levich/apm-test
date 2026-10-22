import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select

from apm import certificates
from apm.compiler import Compiler
from apm.db import Job, Resource, User, now
from apm.schemas import Certificate


def material():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=60))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("example.com"), x509.DNSName("*.example.com")]), False
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM), key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def installed(config):
    resource_id = str(uuid.uuid4())
    pem, key = material()
    data = certificates.install_certificate(config, resource_id, pem, key, ["example.com"])
    return (
        Resource(
            id=resource_id,
            name="test",
            kind="certificates",
            enabled=True,
            data=Certificate(**data, mode="http", terms_agreed=True).model_dump(),
        ),
        pem,
        key,
    )


def test_validity_dates_san_wildcards_and_expiry(config, monkeypatch):
    assert certificates.covered("APP.example.com.", ["*.EXAMPLE.COM"])
    assert not certificates.covered("example.com", ["*.example.com"])
    obj, _, _ = installed(config)
    info = certificates.certificate_info(config, obj, ["app.example.com"])
    assert info["status"] == "valid"
    assert info["remaining_days"] == 60
    assert info["not_before"] < now() < info["expires_at"]
    assert certificates.certificate_info(config, obj, ["deep.app.example.com"])["status"] == "domain_mismatch"
    monkeypatch.setattr(certificates, "now", lambda: info["expires_at"] - 29 * 86400)
    assert certificates.certificate_info(config, obj)["status"] == "expiring"
    monkeypatch.setattr(certificates, "now", lambda: info["expires_at"])
    assert certificates.certificate_info(config, obj)["status"] == "expired"
    monkeypatch.setattr(certificates, "now", lambda: info["not_before"] - 1)
    assert certificates.certificate_info(config, obj)["status"] == "not_yet_valid"


def test_bad_material_disabled_and_missing(config):
    obj, _, _ = installed(config)
    directory = config.data_dir / "certificates" / obj.id / obj.data["fingerprint"]
    _, other_key = material()
    (directory / "privkey.pem").write_bytes(other_key)
    assert certificates.certificate_info(config, obj)["status"] == "key_mismatch"
    (directory / "fullchain.pem").write_text("broken")
    assert certificates.certificate_info(config, obj)["status"] == "invalid_files"
    obj.enabled = False
    assert certificates.certificate_info(config, obj)["status"] == "disabled"
    assert certificates.certificate_info(config, None)["status"] == "missing"


def managed_certificate(admin, config):
    obj, pem, key = installed(config)
    with admin.app.state.db.session() as session:
        session.add(obj)
    return obj, pem, key


def test_manual_renewal_deduplicates_concurrent_requests_and_preserves_material(admin, config):
    obj, _, _ = managed_certificate(admin, config)
    url = f"/api/v1/resources/certificates/{obj.id}/renew"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: admin.post(url), range(2)))
    assert sorted(response.status_code for response in results) == [202, 409]
    rows = admin.get("/api/v1/resources/certificates").json()
    assert rows[0]["certificate_info"]["status"] == "valid"
    assert rows[0]["active_operation"]["status"] == "pending"
    assert rows[0]["data"]["status"] == "ready"
    with admin.app.state.db.session() as session:
        jobs = session.scalars(select(Job).where(Job.kind == "certificate.issue")).all()
        assert len(jobs) == 1
        assert jobs[0].payload["force"] is True
        assert jobs[0].payload["_context"]["name"] == "test"
    operation = admin.get("/api/v1/operations").json()[0]
    assert "Перевыпуск" in operation["title"]
    assert operation["subject"]["name"] == "test"


@pytest.mark.parametrize("mode,enabled", [("custom", True), ("http", False)])
def test_manual_renewal_rejects_custom_and_disabled(admin, config, mode, enabled):
    obj, _, _ = installed(config)
    obj.data = {**obj.data, "mode": mode}
    obj.enabled = enabled
    with admin.app.state.db.session() as session:
        session.add(obj)
    assert admin.post(f"/api/v1/resources/certificates/{obj.id}/renew").status_code == 422


@pytest.mark.parametrize("role", ["operator", "observer"])
def test_manual_renewal_requires_admin(admin, config, role):
    obj, _, _ = managed_certificate(admin, config)
    with admin.app.state.db.session() as session:
        session.scalar(select(User)).role = role
    assert admin.post(f"/api/v1/resources/certificates/{obj.id}/renew").status_code == 403


@pytest.mark.parametrize("force", [True, False])
def test_certbot_force_flag_and_success_queues_apply(admin, config, monkeypatch, force):
    obj, pem, key = managed_certificate(admin, config)
    live = config.data_dir / "acme/config/live" / obj.id
    live.mkdir(parents=True)
    (live / "fullchain.pem").write_bytes(pem)
    (live / "privkey.pem").write_bytes(key)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    result = certificates.issue(admin.app.state.db, config, obj.id, force=force)
    assert ("--force-renewal" in commands[0]) is force
    assert ("--keep-until-expiring" in commands[0]) is not force
    assert result["certificate_id"] == obj.id
    with admin.app.state.db.session() as session:
        assert session.scalar(select(Job).where(Job.kind == "apply")).payload["_context"]["name"] == "test"


def test_failed_reissue_keeps_usable_certificate(admin, config, monkeypatch):
    obj, _, _ = managed_certificate(admin, config)
    fingerprint = obj.data["fingerprint"]
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match="Certbot"):
        certificates.issue(admin.app.state.db, config, obj.id, force=True)
    row = admin.get("/api/v1/resources/certificates").json()[0]
    assert row["data"]["status"] == "error"
    assert row["data"]["fingerprint"] == fingerprint
    assert row["certificate_info"]["status"] == "valid"
    compiler = Compiler(config, {}, config.data_dir)
    compiler.resources = {obj.id: {"id": obj.id, "kind": "certificates", "data": row["data"]}}
    assert compiler.certificate(obj.id).is_dir()


def test_certbot_timeout_retains_material_and_reports_failed_issuance(admin, config, monkeypatch):
    obj, _, _ = managed_certificate(admin, config)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("certbot", 3600)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        certificates.issue(admin.app.state.db, config, obj.id, force=True)
    item = admin.get("/api/v1/resources/certificates").json()[0]
    assert item["data"]["status"] == "error"
    assert item["certificate_info"]["status"] == "valid"
