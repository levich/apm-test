"""Offline source snapshots, conservative import, and encrypted full backups."""

import base64
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import HTTPException
from sqlalchemy import select

from apm.db import Resource, uid
from apm.schemas import SCHEMAS
from apm.security import Vault, atomic_write
from apm.services import audit, check_references, conflicts, enqueue_apply

TABLES = (
    "proxy_host",
    "redirection_host",
    "dead_host",
    "stream",
    "certificate",
    "access_list",
    "access_list_auth",
    "access_list_client",
    "npmplus_proxy_host_access_list",
    "migrations",
    "knex_migrations",
)


def export_sqlite(source: Path):
    uri = source.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            "format": "apm-npm-snapshot-v1",
            "source": "sqlite",
            "tables": {
                table: [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                for table in TABLES
                if table in tables
            },
        }


def export_postgres(dsn):
    import psycopg
    from psycopg.rows import dict_row

    # The only transaction against the source is a consistent read-only snapshot.
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        tables = {
            row["table_name"]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
        }
        return {
            "format": "apm-npm-snapshot-v1",
            "source": "postgresql",
            "tables": {
                table: connection.execute(f'SELECT * FROM "{table}"').fetchall()
                for table in TABLES
                if table in tables
            },
        }


def decoded(value, default):
    if value in (None, ""):
        return default
    return json.loads(value) if isinstance(value, str) else value


def convert(document):
    if document.get("format") != "apm-npm-snapshot-v1":
        raise ValueError("Unsupported snapshot format; use apm export-npm")
    tables = document.get("tables", {})
    if "proxy_host" not in tables or "access_list" not in tables:
        raise ValueError("Unknown source schema: proxy_host/access_list tables are required")
    resources, blockers, warnings = [], [], []
    mapping = {}

    def add(kind, row, data, secret=None):
        object_id = uid()
        source_key = f"import:{kind}:{row['id']}"
        mapping[(kind, int(row["id"]))] = object_id
        validated = SCHEMAS[kind].model_validate(data).model_dump(mode="json")
        resources.append(
            {
                "id": object_id,
                "kind": kind,
                "name": row.get("name") or ", ".join(data.get("domains", [])) or source_key,
                "data": validated,
                "source_key": source_key,
                "secret": secret,
                "enabled": bool(row.get("enabled", True)),
            }
        )

    def active(table):
        return [row for row in tables.get(table, []) if not row.get("is_deleted")]

    for row in active("access_list"):
        clients = [
            c
            for c in tables.get("access_list_client", [])
            if c.get("access_list_id") == row["id"] and not c.get("is_deleted")
        ]
        users = [
            a
            for a in tables.get("access_list_auth", [])
            if a.get("access_list_id") == row["id"] and not a.get("is_deleted")
        ]
        credentials = {a["username"]: a["password"] for a in users}
        for value in credentials.values():
            if not value.startswith(("$2y$", "$2b$", "$apr1$", "$6$")):
                blockers.append(f"access_list:{row['id']}: unsupported password hash")
        rules = [
            {"address": c["address"], "action": c["directive"]}
            for c in sorted(clients, key=lambda c: c.get("id", 0))
        ]
        # NPM emits a terminal deny when clients are configured. Preserve this.
        if rules and rules[-1]["address"] != "all":
            rules.append({"address": "all", "action": "deny"})
        add(
            "access-lists",
            row,
            {
                "rules": rules,
                "users": sorted(credentials),
                "satisfy": "any" if row.get("satisfy_any") else "all",
                "pass_auth": bool(row.get("pass_auth")),
            },
            credentials,
        )

    for row in active("certificate"):
        domains = decoded(row.get("domain_names"), [])
        add("certificates", row, {"domains": domains, "mode": "custom"})
        material = document.get("certificate_files", {}).get(str(row["id"]))
        if material:
            resources[-1]["pem"] = material
        else:
            warnings.append(f"certificate:{row['id']}: source PEM chain and key are missing")

    for table, kind in (
        ("proxy_host", "proxy-hosts"),
        ("redirection_host", "redirect-hosts"),
        ("stream", "streams"),
    ):
        for row in active(table):
            source = f"{table}:{row['id']}"
            try:
                advanced = row.get("advanced_config") or ""
                if advanced.strip():
                    blockers.append(source + ": custom directives require manual review")
                meta = decoded(row.get("meta"), {})
                # Unknown security extensions must never become public routes silently.
                safe_flags = {"npmplus_access_list_ids", "npmplus_access_list_type"}
                for field, value in row.items():
                    if (
                        field.startswith("npmplus_")
                        and field not in safe_flags
                        and value not in (None, False, 0, "", "[]", "{}")
                    ):
                        blockers.append(source + ": unsupported extension " + field)
                if any(
                    value
                    for key, value in meta.items()
                    if any(term in key.lower() for term in ("auth", "crowdsec", "waf", "geo", "captcha"))
                ):
                    blockers.append(source + ": external protection requires manual review")
                certificate_id = mapping.get(("certificates", int(row.get("certificate_id") or 0)))
                if row.get("certificate_id") and str(row["certificate_id"]) not in document.get(
                    "certificate_files", {}
                ):
                    blockers.append(
                        source + ": certificate PEM material must be uploaded after importing drafts"
                    )
                if row.get("block_exploits"):
                    blockers.append(source + ": review the source exploit-blocking directives")
                if kind == "proxy-hosts":
                    if not {"forward_host", "forward_port", "domain_names"}.issubset(row):
                        raise ValueError("unknown proxy schema")
                    access_ids = decoded(row.get("npmplus_access_list_ids"), [])
                    acl_type = row.get("npmplus_access_list_type")
                    if acl_type == "custom":
                        linked = {
                            j["access_list_id"]
                            for j in tables.get("npmplus_proxy_host_access_list", [])
                            if j["proxy_host_id"] == row["id"]
                        }
                        if not access_ids or set(access_ids) != linked:
                            blockers.append(source + ": inconsistent multi-ACL references")
                    elif row.get("access_list_id"):
                        access_ids = [row["access_list_id"]]
                    if any(("access-lists", int(i)) not in mapping for i in access_ids):
                        blockers.append(source + ": missing access list")
                    locations = decoded(row.get("locations"), [])
                    if any(loc.get("advanced_config") for loc in locations):
                        blockers.append(source + ": custom location directives require manual review")
                    data = {
                        "domains": decoded(row["domain_names"], []),
                        "host": row["forward_host"],
                        "port": row["forward_port"],
                        "scheme": row.get("forward_scheme", "http"),
                        "tls": "certificate" if certificate_id else "off",
                        "certificate_id": certificate_id,
                        "force_ssl": bool(row.get("ssl_forced")),
                        "websocket": bool(row.get("allow_websocket_upgrade")),
                        "http2": bool(row.get("http2_support")),
                        "access_ids": [
                            mapping[("access-lists", int(i))]
                            for i in access_ids
                            if ("access-lists", int(i)) in mapping
                        ],
                        "locations": [
                            {
                                "path": loc["path"],
                                "host": loc["forward_host"],
                                "port": loc["forward_port"],
                                "scheme": loc.get("forward_scheme", "http"),
                            }
                            for loc in locations
                        ],
                    }
                    if acl_type not in (None, "public", "custom"):
                        blockers.append(source + ": unsupported access inheritance mode")
                elif kind == "redirect-hosts":
                    data = {
                        "domains": decoded(row["domain_names"], []),
                        "target": row.get("forward_scheme", "https") + "://" + row["forward_domain_name"],
                        "code": int(row.get("forward_http_code", 301)),
                        "preserve_uri": bool(row.get("preserve_path", True)),
                        "certificate_id": certificate_id,
                    }
                else:
                    if row.get("tcp_forwarding") and row.get("udp_forwarding"):
                        blockers.append(source + ": combined TCP/UDP stream must be split explicitly")
                    data = {
                        "listen_port": row["incoming_port"],
                        "host": row["forwarding_host"],
                        "port": row["forwarding_port"],
                        "protocol": "udp" if row.get("udp_forwarding") else "tcp",
                    }
                add(kind, row, data)
            except (ValueError, KeyError, TypeError):
                blockers.append(source + ": unsupported or invalid source data")
    if active("dead_host"):
        blockers.append("dead_host: review default/dead host policy manually")
    return {"resources": resources, "blockers": sorted(set(blockers)), "warnings": warnings}


def preview(config, data: bytes):
    try:
        document = json.loads(data)
        report = convert(document)
        from apm.certificates import install_certificate

        for obj in report["resources"]:
            if material := obj.pop("pem", None):
                obj["data"].update(
                    install_certificate(
                        config,
                        obj["id"],
                        material["fullchain"].encode(),
                        material["private_key"].encode(),
                        obj["data"]["domains"],
                    )
                )
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error
    import_id = uid()
    directory = config.data_dir / "imports"
    directory.mkdir(exist_ok=True, mode=0o700)
    atomic_write(directory / (import_id + ".json.enc"), Vault(config.data_dir).encrypt(report).encode())
    return {
        "import_id": import_id,
        "objects": [{k: obj[k] for k in ("kind", "name", "enabled")} for obj in report["resources"]],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "can_activate": not report["blockers"],
    }


def activate(session, config, user, import_id, drafts=False):
    try:
        import_id = str(uuid.UUID(import_id))
        path = config.data_dir / "imports" / (import_id + ".json.enc")
        report = Vault(config.data_dir).decrypt(path.read_text())
    except (ValueError, OSError):
        raise HTTPException(404, "Import not found") from None
    if report["blockers"] and not drafts:
        raise HTTPException(409, {"blockers": report["blockers"]})
    for obj in report["resources"]:
        if session.scalar(select(Resource.id).where(Resource.source_key == obj["source_key"])):
            raise HTTPException(409, "Source object already imported")
        if obj["enabled"] and not drafts:
            conflicts(session, obj["kind"], obj["data"])
        session.add(
            Resource(
                id=obj["id"],
                kind=obj["kind"],
                name=obj["name"],
                data=obj["data"],
                enabled=obj["enabled"] and not drafts,
                source="import",
                source_key=obj["source_key"],
                secret=Vault(config.data_dir).encrypt(obj["secret"]) if obj["secret"] else None,
            )
        )
        session.flush()
    if not drafts:
        for obj in report["resources"]:
            check_references(session, obj["data"])
    audit(session, user, "import.activate", import_id, count=len(report["resources"]))
    return enqueue_apply(session)


def archive_key(password: bytes, salt: bytes):
    return base64.urlsafe_b64encode(Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password))


def backup(database, config, backup_id):
    backup_id = str(uuid.UUID(backup_id))
    password_file = config.data_dir / "backup.password"
    if not password_file.exists():
        raise ValueError("Set a backup password with apm backup-password first")
    root = config.data_dir
    with tempfile.TemporaryDirectory(prefix="apm-backup-") as scratch:
        snapshot = Path(scratch) / "apm.sqlite3"
        with sqlite3.connect(root / "apm.sqlite3") as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            archive.add(snapshot, arcname="apm.sqlite3")
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if (
                    relative.parts[0] in ("run", "exports", "logs")
                    or relative.parts[0].startswith((".before-restore-", ".apm-restore-"))
                    or path.name.startswith("apm.sqlite3")
                    or path.name == "backup.password"
                    or path.is_symlink()
                    or not path.is_file()
                ):
                    continue
                archive.add(path, arcname=str(relative), recursive=False)
        salt = os.urandom(16)
        encrypted = (
            b"APM1"
            + salt
            + Fernet(archive_key(password_file.read_bytes().strip(), salt)).encrypt(stream.getvalue())
        )
        path = root / "exports" / (backup_id + ".apm")
        atomic_write(path, encrypted)
    return {
        "backup_id": backup_id,
        "bytes": len(encrypted),
        "download_url": f"/api/v1/backups/{backup_id}/download",
    }


def restore(archive: Path, destination: Path, password: str):
    payload = archive.read_bytes()
    if payload[:4] != b"APM1":
        raise ValueError("Unknown backup format")
    try:
        plain = Fernet(archive_key(password.encode(), payload[4:20])).decrypt(payload[20:])
    except InvalidToken:
        raise ValueError("Invalid backup password or corrupted archive") from None
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True, mode=0o750)
    journal = destination / ".restore-journal.json"
    if journal.exists():
        raise ValueError(
            "An interrupted restore needs local inspection of .restore-journal.json before retrying"
        )
    # Staging and the preserved copy remain inside the bind mount; never rename /data.
    staging = Path(tempfile.mkdtemp(prefix=".apm-restore-", dir=destination))
    try:
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as bundle:
            members = bundle.getmembers()
            if sum(m.size for m in members) > 8 * 1024**3:
                raise ValueError("Backup exceeds the extraction limit")
            for member in members:
                if not member.isfile() or Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                    raise ValueError("Unsafe backup entry")
            bundle.extractall(staging, filter="data")
        with sqlite3.connect(staging / "apm.sqlite3") as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed integrity check")
        if not (staging / "master.key").is_file():
            raise ValueError("Backup is missing its encryption key")
        # Absolute revision paths belong to the old host. Re-render from desired state.
        for name in ("angie.conf", "current"):
            (staging / name).unlink(missing_ok=True)
        with sqlite3.connect(staging / "apm.sqlite3") as connection:
            connection.execute("DELETE FROM sessions")
            connection.execute(
                "UPDATE jobs SET status='failed', error='Interrupted by restore' "
                "WHERE status IN ('pending','running','awaiting_confirmation')"
            )
            connection.execute(
                "DELETE FROM state WHERE key IN ('applied','apply_halted','agent_status','capabilities')"
            )
        previous = destination / (".before-restore-" + uuid.uuid4().hex[:8])
        previous.mkdir(mode=0o700)
        old_files = [
            path.name
            for path in destination.iterdir()
            if path not in (staging, previous, journal)
            and path.name != "run"
            and not path.name.startswith(".before-restore-")
        ]
        new_files = [path.name for path in staging.iterdir()]
        atomic_write(
            journal,
            json.dumps(
                {
                    "phase": "moving_old",
                    "previous": previous.name,
                    "staging": staging.name,
                    "old_files": old_files,
                    "new_files": new_files,
                }
            ).encode(),
        )
        try:
            for name in old_files:
                (destination / name).rename(previous / name)
            atomic_write(
                journal,
                json.dumps(
                    {
                        "phase": "installing_new",
                        "previous": previous.name,
                        "staging": staging.name,
                        "old_files": old_files,
                        "new_files": new_files,
                    }
                ).encode(),
            )
            for name in new_files:
                (staging / name).rename(destination / name)
            run = destination / "run"
            if run.exists():
                for path in run.iterdir():
                    if path.name != "maintenance.lock" and not path.is_dir():
                        path.unlink(missing_ok=True)
            journal.unlink()
        except Exception:
            # Keep the journal and staging for an offline repair after a failed swap.
            raise
        return str(previous)
    finally:
        if staging.exists() and not journal.exists():
            shutil.rmtree(staging)
