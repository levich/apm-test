import time

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
