import fcntl
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import typer
from sqlalchemy import delete, select

from apm.config import Settings
from apm.db import Database, LoginSession, User, state_set, uid
from apm.security import atomic_write, passwords

app = typer.Typer(no_args_is_help=True, help="Local administration of Angie Proxy Manager")


def database(config):
    db = Database(config)
    db.initialize()
    return db


@contextmanager
def offline(config):
    config.prepare()
    with (config.data_dir / "run/maintenance.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise typer.BadParameter("Stop manager and worker before this operation") from None
        yield


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8181):
    """Run the manager (publish this port on loopback only)."""
    import uvicorn

    uvicorn.run(
        "apm.main:create_app",
        factory=True,
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        access_log=False,
    )


@app.command()
def worker(once: bool = False):
    from apm.worker import Worker

    config = Settings()
    db = database(config)
    from apm.services import enqueue_apply

    with db.session() as session:
        from apm.db import Revision

        if not session.scalar(select(Revision.id).limit(1)):
            enqueue_apply(session)
    process = Worker(config, db)
    if once:
        with process.exclusive():
            process.recover()
            process.tick()
    else:
        process.run()


@app.command()
def agent():
    import uvicorn

    config = Settings()
    config.prepare()
    os.umask(0o007)
    uvicorn.run("apm.agent:create_agent", factory=True, uds=str(config.socket), access_log=False)


@app.command()
def bootstrap_agent():
    from apm.agent import Agent

    Agent(Settings()).initialize()


@app.command()
def pre_run():
    """Execute deployment-owned scripts; no HTTP endpoint can add hooks."""
    import re
    import subprocess

    directory = Settings().pre_run_dir
    if not directory.is_dir():
        return
    for script in sorted(directory.iterdir()):
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+\.sh", script.name)
            or script.is_symlink()
            or not script.is_file()
        ):
            raise typer.BadParameter("Unsafe hook entry")
        if script.stat().st_mode & 0o022:
            raise typer.BadParameter("Hooks must not be group/world writable")
        result = subprocess.run(["/bin/sh", str(script)], timeout=60, capture_output=True)
        if result.returncode:
            raise typer.BadParameter("Pre-run hook failed: " + script.name)


@app.command()
def setup_token():
    """Print the one-time token locally; never exposes it through HTTP."""
    from apm.services import bootstrap_token

    config = Settings()
    db = database(config)
    with db.session() as session:
        typer.echo(bootstrap_token(session, config.data_dir))


@app.command()
def migrate():
    database(Settings())
    typer.echo("Database is at the current migration")


@app.command()
def backup_password():
    config = Settings()
    config.prepare()
    value = typer.prompt(
        "Archive password (minimum 16 characters)", hide_input=True, confirmation_prompt=True
    )
    if len(value) < 16:
        raise typer.BadParameter("Password too short")
    atomic_write(config.data_dir / "backup.password", value.encode())
    typer.echo("Backup password saved locally")


@app.command()
def backup():
    from apm.transfers import backup as create_backup

    config = Settings()
    db = database(config)
    with offline(config):
        result = create_backup(db, config, uid())
    typer.echo(str(config.data_dir / "exports" / (result["backup_id"] + ".apm")))


@app.command()
def restore(archive: Path):
    """Restore offline; preserves the previous data directory for recovery."""
    from apm.services import enqueue_apply
    from apm.transfers import restore as restore_backup

    config = Settings()
    password = typer.prompt("Archive password", hide_input=True)
    with offline(config):
        previous = restore_backup(archive.resolve(), config.data_dir, password)
        db = database(config)
        with db.session() as session:
            enqueue_apply(session)
    typer.echo(f"Restored. Previous directory: {previous}. Start services to validate and apply.")


@app.command()
def reset_password(email: str, reset_mfa: bool = False):
    config = Settings()
    db = database(config)
    password = typer.prompt("New password", hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        raise typer.BadParameter("Password must have at least 12 characters")
    with db.session() as session:
        user = session.scalar(select(User).where(User.email == email.lower()))
        if not user:
            raise typer.BadParameter("User not found")
        user.password_hash = passwords.hash(password)
        if reset_mfa:
            user.totp_secret, user.recovery_hashes = None, []
        session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        from apm.services import audit

        audit(session, "local-cli", "user.recovery", user.id, mfa_reset=reset_mfa)
    typer.echo("Password changed; all user sessions revoked")


@app.command()
def resume_applies():
    """Use after locally repairing Angie and inspecting the apply journal."""
    config = Settings()
    db = database(config)
    from apm.agent import Agent
    from apm.db import Job, Revision, now
    from apm.services import sync_safety

    agent = Agent(config)
    with agent.lock():
        if (config.data_dir / "run/apply-journal.json").exists():
            raise typer.BadParameter("Resolve the agent apply journal first")
        with db.session() as session:
            sync_safety(session, agent.read_json("safety-status.json", {}))
            # Queued snapshots can still contain the rejected settings. Require a fresh apply.
            for job in session.scalars(select(Job).where(Job.kind == "apply", Job.status == "pending")):
                job.status, job.error, job.updated_at = "failed", "Cancelled during local safety recovery", now()
                revision = session.get(Revision, job.payload.get("revision_id"))
                if revision:
                    revision.status, revision.error = "failed", job.error
            state_set(session, "apply_halted", {"halted": False})
        (config.data_dir / "run/safety-halted.json").unlink(missing_ok=True)
    typer.echo("Apply queue resumed; stale queued applies cancelled. Review the desired settings and save again.")


@app.command()
def safety_status():
    """Inspect the local safety journal without manager, worker or HTTP access."""
    from apm.agent import Agent

    typer.echo(json.dumps(Agent(Settings()).safety(), indent=2))


@app.command()
def safety_rollback():
    """Restore the confirmed revision from an outstanding/failed trial locally."""
    from apm.agent import Agent

    agent = Agent(Settings())
    with agent.lock():
        state = agent.read_json("apply-journal.json")
        if not state:
            raise typer.BadParameter("No trial or recovery journal exists")
        typer.echo(json.dumps(agent.rollback(state, "local_cli"), indent=2))


@app.command()
def safety_watchdog():
    """Run recovery independently of the Unix API and its HTTP server."""
    from apm.agent import Agent

    agent = Agent(Settings())
    with agent.lock():
        try:
            agent.recover()
        except RuntimeError:
            pass
    agent.watch(threading.Event())


@app.command()
def export_npm(
    output: Path, sqlite: Path | None = None, postgres: bool = False, certificates: Path | None = None
):
    """Export a read-only SQLite or PostgreSQL source; DSN is never retained."""
    from apm.transfers import export_postgres, export_sqlite

    if bool(sqlite) == postgres:
        raise typer.BadParameter("Choose --sqlite PATH or --postgres")
    document = (
        export_postgres(typer.prompt("PostgreSQL DSN", hide_input=True))
        if postgres
        else export_sqlite(sqlite)
    )
    if certificates:
        root = certificates.resolve()
        material = {}
        for row in document["tables"].get("certificate", []):
            directory = root / "live" / ("npm-" + str(int(row["id"])))
            paths = [directory / "fullchain.pem", directory / "privkey.pem"]
            if all(path.is_file() and path.resolve().is_relative_to(root) for path in paths):
                material[str(row["id"])] = {
                    "fullchain": paths[0].read_text(),
                    "private_key": paths[1].read_text(),
                }
        document["certificate_files"] = material
    if output.exists():
        raise typer.BadParameter("Output already exists")
    atomic_write(output.resolve(), json.dumps(document, default=str).encode())
    typer.echo("Snapshot saved with mode 0600. Upload it on the Imports page.")


@app.command()
def gateway(host: str = "0.0.0.0", port: int = 2375):
    import uvicorn

    uvicorn.run("apm.gateway:create_gateway", factory=True, host=host, port=port, access_log=False)


if __name__ == "__main__":
    app()
