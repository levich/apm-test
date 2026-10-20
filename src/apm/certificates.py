import hashlib
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select

from apm.db import Job, Resource, now
from apm.schemas import Certificate
from apm.security import Vault, atomic_write
from apm.services import audit, enqueue, enqueue_apply


def covered(domain, names):
    if domain in names:
        return True
    return any(
        n.startswith("*.") and domain.count(".") == n.count(".") and domain.endswith(n[1:]) for n in names
    )


def install_certificate(config, resource_id, cert_pem, key_pem, domains):
    certificates = x509.load_pem_x509_certificates(cert_pem)
    if not certificates:
        raise ValueError("Certificate chain is empty")
    leaf = certificates[0]
    key = serialization.load_pem_private_key(key_pem, password=None)
    if key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) != leaf.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ):
        raise ValueError("Private key does not match certificate")
    current = datetime.now(UTC)
    if not leaf.not_valid_before_utc <= current < leaf.not_valid_after_utc:
        raise ValueError("Certificate is not currently valid")
    try:
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName) + [
            str(v) for v in san.get_values_for_type(x509.IPAddress)
        ]
    except x509.ExtensionNotFound:
        names = []
    if not all(covered(domain, names) for domain in domains):
        raise ValueError("Certificate does not cover all configured domains")
    cert_pem = b"".join(c.public_bytes(serialization.Encoding.PEM) for c in certificates)
    fingerprint = hashlib.sha256(cert_pem).hexdigest()
    directory = config.data_dir / "certificates" / resource_id / fingerprint
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    atomic_write(directory / "fullchain.pem", cert_pem, 0o640)
    atomic_write(
        directory / "chain.pem",
        b"".join(c.public_bytes(serialization.Encoding.PEM) for c in certificates[1:]) or cert_pem,
        0o640,
    )
    atomic_write(
        directory / "privkey.pem",
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
        0o640,
    )
    return {
        "fingerprint": fingerprint,
        "expires_at": int(leaf.not_valid_after_utc.timestamp()),
        "status": "ready",
        "domains": names,
    }


def install_ca(config, resource_id, pem, crl_pem=None):
    cert = x509.load_pem_x509_certificate(pem)
    if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Certificate is not a CA")
    if crl_pem:
        crl = x509.load_pem_x509_crl(crl_pem)
        if crl.issuer != cert.subject or not crl.is_signature_valid(cert.public_key()):
            raise ValueError("CRL was not signed by the selected CA")
        if not crl.next_update_utc or crl.next_update_utc <= datetime.now(UTC):
            raise ValueError("CRL has expired")
    fingerprint = hashlib.sha256(pem + (crl_pem or b"")).hexdigest()
    atomic_write(config.data_dir / "certificates" / resource_id / fingerprint / "ca.pem", pem, 0o640)
    if crl_pem:
        atomic_write(config.data_dir / "certificates" / resource_id / fingerprint / "crl.pem", crl_pem, 0o640)
    return {"fingerprint": fingerprint}


def issue(database, config, resource_id):
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        if not resource or resource.kind != "certificates":
            raise ValueError("Certificate not found")
        data = Certificate.model_validate(resource.data)
        credentials = Vault(config.data_dir).decrypt(resource.secret) if resource.secret else {}
        if data.mode == "custom" or not data.domains or not data.terms_agreed:
            raise ValueError("Managed certificate and explicit ACME terms agreement required")
    directory = config.data_dir / "acme"
    command = [
        config.certbot_binary,
        "certonly",
        "--non-interactive",
        "--keep-until-expiring",
        "--agree-tos",
        "--cert-name",
        resource_id,
        "--config-dir",
        str(directory / "config"),
        "--work-dir",
        str(directory / "work"),
        "--logs-dir",
        str(directory / "logs"),
        "--server",
        data.server,
        "--key-type",
        data.key_type,
    ]
    if data.email:
        command += ["--email", data.email]
    else:
        command += ["--register-unsafely-without-email"]
    for domain in data.domains:
        command += ["-d", domain]
    if data.mode == "http":
        command += ["--webroot", "--webroot-path", str(config.data_dir / "webroot")]
    else:
        command += [
            "--manual",
            "--preferred-challenges",
            "dns",
            "--manual-auth-hook",
            shlex.join([sys.executable, "-m", "apm.hooks", "auth"]),
            "--manual-cleanup-hook",
            shlex.join([sys.executable, "-m", "apm.hooks", "cleanup"]),
        ]
    if data.profile:
        command += ["--required-profile", data.profile]
    if data.reuse_key:
        command += ["--reuse-key"]
    if data.must_staple:
        command += ["--must-staple"]
    if credentials.get("eab_kid") or credentials.get("eab_hmac_key"):
        if not credentials.get("eab_kid") or not credentials.get("eab_hmac_key"):
            raise ValueError("Both EAB credentials are required")
        # Keep EAB material out of process arguments.
        eab = directory / (resource_id + ".ini")
        values = {"eab-kid": credentials["eab_kid"], "eab-hmac-key": credentials["eab_hmac_key"]}
        if any("\n" in value or "\r" in value for value in values.values()):
            raise ValueError("Invalid EAB credentials")
        atomic_write(eab, "\n".join(f"{key} = {value}" for key, value in values.items()).encode())
        command += ["--config", str(eab)]
    environment = {**os.environ, "APM_DATA_DIR": str(config.data_dir), "APM_CERTIFICATE_ID": resource_id}
    try:
        result = subprocess.run(command, env=environment, capture_output=True, timeout=3600)
    finally:
        if credentials.get("eab_kid"):
            eab.unlink(missing_ok=True)
    if result.returncode:
        with database.session() as session:
            resource = session.get(Resource, resource_id)
            resource.data = {**resource.data, "status": "error"}
        raise ValueError("Certbot issuance failed; inspect the local ACME log")
    live = directory / "config/live" / resource_id
    installed = install_certificate(
        config,
        resource_id,
        (live / "fullchain.pem").read_bytes(),
        (live / "privkey.pem").read_bytes(),
        data.domains,
    )
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        resource.data = {**resource.data, **installed}
        resource.version += 1
        audit(session, "worker", "certificate.ready", resource_id, expires_at=installed["expires_at"])
        enqueue_apply(session)
    return {"certificate_id": resource_id, **installed}


def schedule_renewals(database):
    with database.session() as session:
        for resource in session.scalars(
            select(Resource).where(Resource.kind == "certificates", Resource.enabled.is_(True))
        ):
            data = resource.data
            if data.get("mode") == "custom" or not data.get("expires_at"):
                continue
            # Certbot decides whether renewal is due; check short-lived profiles more frequently.
            key = "renew:" + resource.id
            from apm.db import state_get, state_set

            last = state_get(session, key, {}).get("at", 0)
            if last > now() - 3600:
                continue
            active = session.scalar(
                select(Job.id).where(
                    Job.kind == "certificate.issue",
                    Job.status.in_(["pending", "running"]),
                    Job.payload["resource_id"].as_string() == resource.id,
                )
            )
            if not active:
                enqueue(session, "certificate.issue", {"resource_id": resource.id})
                state_set(session, key, {"at": now()})
