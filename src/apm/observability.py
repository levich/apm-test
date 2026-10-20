import json
import time
from pathlib import Path

from apm.db import state_get, state_set


def collect(database, payload, retention_days):
    timestamp = int(time.time())
    with database.session() as session:
        series = state_get(session, "metrics", {"points": []})["points"]
        # Bound the history independently of user-provided API payload sizes.
        connections = payload.get("connections", {})
        requests = payload.get("http", {}).get("requests", {})
        point = {"at": timestamp, "connections": connections, "requests": requests}
        cutoff = timestamp - retention_days * 86400
        points = [p for p in series if p["at"] >= cutoff][-10079:] + [point]
        state_set(session, "metrics", {"points": points})
        state_set(session, "metrics_latest", {"at": timestamp, "data": payload})


def tail(path: Path, maximum=200):
    if not path.is_file():
        return []
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 256 * 1024))
        block = stream.read(256 * 1024).decode(errors="replace")
    rows = []
    for line in block.splitlines()[-maximum:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"message": line[:2000]})
    return rows


def rotate(config, client):
    """Copy-free rotation: rename, then ask the local agent to reopen logs."""
    directory = config.data_dir / "logs"
    changed = False
    for name in ("access.log", "error.log", "analytics.log"):
        path = directory / name
        if path.exists() and path.stat().st_size > 20 * 1024**2:
            path.rename(directory / (name + "." + str(time.time_ns())))
            changed = True
    if changed:
        response = client.post("/logs/reopen")
        response.raise_for_status()
    cutoff = time.time() - config.metrics_retention_days * 86400
    for path in directory.iterdir():
        if path.name not in ("access.log", "error.log", "analytics.log") and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
