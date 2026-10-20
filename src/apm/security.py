import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from pwdlib import PasswordHash

passwords = PasswordHash.recommended()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(value: str, encoded: str) -> bool:
    try:
        return passwords.verify(value, encoded)
    except Exception:
        return False


def atomic_write(path: Path, data: bytes, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def persistent_key(path: Path) -> bytes:
    import fcntl

    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _persistent_key(path)


def _persistent_key(path: Path) -> bytes:
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())
                f.flush()
                os.fsync(f.fileno())
    key = path.read_bytes()
    Fernet(key)
    return key


class Vault:
    def __init__(self, root: Path):
        self.key = persistent_key(root / "master.key")
        self.cipher = Fernet(self.key)

    def encrypt(self, value) -> str:
        return self.cipher.encrypt(json.dumps(value).encode()).decode()

    def decrypt(self, value: str):
        return json.loads(self.cipher.decrypt(value).decode())

    @property
    def cookie_key(self) -> str:
        return base64.urlsafe_b64encode(hashlib.sha256(self.key + b"oauth-state").digest()).decode()
