import sqlite3
import uuid

import pytest

from apm.db import Database, Resource
from apm.dns import Provider, ProviderError
from apm.security import Vault, atomic_write
from apm.transfers import backup, convert, export_sqlite, restore


class MemoryProvider(Provider):
    def values(self, name):
        return self.records.copy()

    def replace(self, name, values):
        self.records = values


def test_dns_only_removes_owned_txt(config):
    provider = MemoryProvider(config, {"zone": "example.com"}, {})
    provider.records = ["unrelated", "existing"]
    first = provider.present("_acme-challenge.example.com", "ours")
    second = provider.present("_acme-challenge.example.com", "existing")
    provider.records.append("concurrent-challenge")
    provider.cleanup(first)
    provider.cleanup(second)
    assert provider.records == ["unrelated", "existing", "concurrent-challenge"]
    with pytest.raises(ProviderError):
        provider.present("_acme-challenge.evil.example", "ours")


def test_source_export_readonly_snapshot(tmp_path):
    path = tmp_path / "npm.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE proxy_host (id INTEGER, domain_names TEXT)")
        connection.execute("CREATE TABLE access_list (id INTEGER)")
        connection.execute("INSERT INTO proxy_host VALUES (1, '[\"example.com\"]')")
    original = path.read_bytes()
    document = export_sqlite(path)
    assert document["tables"]["proxy_host"][0]["id"] == 1
    assert path.read_bytes() == original


def test_import_blocks_inconsistent_multi_acl():
    document = {
        "format": "apm-npm-snapshot-v1",
        "tables": {
            "access_list": [],
            "proxy_host": [
                {
                    "id": 1,
                    "domain_names": '["example.com"]',
                    "forward_host": "127.0.0.1",
                    "forward_port": 8080,
                    "npmplus_access_list_type": "custom",
                    "npmplus_access_list_ids": "[3]",
                }
            ],
        },
    }
    report = convert(document)
    assert any("inconsistent multi-ACL" in issue for issue in report["blockers"])
    assert any("missing access list" in issue for issue in report["blockers"])


def test_backup_restore_retains_secrets_and_invalidates_sessions(config, tmp_path):
    db = Database(config)
    db.initialize()
    vault = Vault(config.data_dir)
    with db.session() as session:
        session.add(
            Resource(
                kind="dns-profiles",
                name="dns",
                data={"zone": "example.com"},
                secret=vault.encrypt({"token": "secret-value"}),
            )
        )
    atomic_write(config.data_dir / "backup.password", b"backup-password-long-enough")
    result = backup(db, config, str(uuid.uuid4()))
    path = config.data_dir / "exports" / (result["backup_id"] + ".apm")
    assert b"secret-value" not in path.read_bytes()
    with pytest.raises(ValueError, match="password"):
        restore(path, tmp_path / "wrong", "wrong-password")
    target = tmp_path / "restored"
    restore(path, target, "backup-password-long-enough")
    with sqlite3.connect(target / "apm.sqlite3") as connection:
        encrypted = connection.execute("SELECT secret FROM resources").fetchone()[0]
    assert Vault(target).decrypt(encrypted) == {"token": "secret-value"}
