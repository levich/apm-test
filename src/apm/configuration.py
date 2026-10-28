"""Read the selected immutable configuration, excluding credential sidecars."""

import re
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

CONFIG_PATH = re.compile(
    r"(?:angie|http|stream)\.conf|(?:http|stream)/[A-Za-z0-9_-]+\.(?:proxy|redirect|stream|site|upstream)\.conf"
)
MAX_FILE_BYTES = 2_000_000


def active_directory(data_dir: Path):
    link = data_dir / "current"
    if not link.is_symlink():
        return None
    directory = link.resolve()
    try:
        revision = str(UUID(directory.name))
    except ValueError:
        raise HTTPException(409, "Invalid active configuration") from None
    expected = data_dir / "revisions" / revision
    if directory != expected or expected.is_symlink() or not directory.is_dir():
        raise HTTPException(409, "Active configuration is unavailable")
    return directory


def configuration_path(directory, name):
    if not CONFIG_PATH.fullmatch(name):
        raise HTTPException(404, "Configuration file not found")
    path = directory / name
    if any(part.is_symlink() for part in (path, path.parent)) or not path.is_file():
        raise HTTPException(404, "Configuration file not found")
    return path


def list_configuration(config):
    directory = active_directory(config.data_dir)
    files = []
    if directory:
        candidates = list(directory.glob("*.conf"))
        for scope in ("http", "stream"):
            if not (directory / scope).is_symlink():
                candidates.extend((directory / scope).glob("*.conf"))
        for path in candidates:
            name = path.relative_to(directory).as_posix()
            if CONFIG_PATH.fullmatch(name) and not path.is_symlink() and path.is_file():
                files.append({"path": name, "size": path.stat().st_size})
    return {"revision_id": directory.name if directory else None, "mode": config.angie_mode,
            "files": sorted(files, key=lambda item: (item["path"] != "angie.conf", item["path"]))}


def read_configuration(config, revision_id, name):
    directory = active_directory(config.data_dir)
    if not directory or directory.name != str(revision_id):
        raise HTTPException(409, "Active configuration changed; refresh the file list")
    path = configuration_path(directory, name)
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(413, "Configuration file is too large to display")
        contents = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise HTTPException(409, "Configuration file is unavailable") from None
    if active_directory(config.data_dir) != directory:
        raise HTTPException(409, "Active configuration changed; refresh the file list")
    return {"revision_id": directory.name, "path": name, "content": contents}
