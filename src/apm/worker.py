import fcntl
import logging
import time
from contextlib import contextmanager

import httpx
from sqlalchemy import select, update

from apm.compiler import Compiler
from apm.config import Settings
from apm.db import Database, Job, Resource, Revision, State, now, state_get, state_set
from apm.security import Vault
from apm.services import audit

logger = logging.getLogger("apm.worker")


class Worker:
    def __init__(self, config: Settings, database=None):
        self.config = config
        self.db = database or Database(config)
        self.vault = Vault(config.data_dir)
        self.http = httpx.Client(
            transport=httpx.HTTPTransport(uds=str(config.socket)), base_url="http://agent", timeout=60
        )

    @contextmanager
    def exclusive(self):
        with (
            (self.config.data_dir / "run/worker.lock").open("a") as f,
            (self.config.data_dir / "run/maintenance.lock").open("a") as maintenance,
        ):
            fcntl.flock(maintenance, fcntl.LOCK_SH)
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another worker is already running") from None
            yield

    def claim(self):
        with self.db.session() as s:
            query = select(Job).where(Job.status == "pending", Job.available_at <= now())
            if state_get(s, "apply_halted", {}).get("halted"):
                query = query.where(Job.kind != "apply")
            job = s.scalar(query.order_by(Job.sequence).limit(1))
            if not job:
                return None
            result = s.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "pending")
                .values(
                    status="running", attempts=Job.attempts + 1, lease_until=now() + 7200, updated_at=now()
                )
            )
            return job.id if result.rowcount else None

    def recover(self):
        with self.db.session() as s:
            # A process-wide flock proves no predecessor is still running.
            s.execute(update(Job).where(Job.status == "running").values(status="pending", lease_until=0))
            from apm.services import enqueue

            for challenge in s.scalars(select(State).where(State.key.like("challenge:%"))):
                if not challenge.value.get("cleaned"):
                    job = enqueue(s, "dns.cleanup", {"state_key": challenge.key})
                    job.sequence = 0

    def capabilities(self):
        response = self.http.get("/capabilities")
        response.raise_for_status()
        caps = response.json()
        with self.db.session() as s:
            cached = state_get(s, "cloudflare_cidrs", {})
            caps["cloudflare_cidrs"] = cached.get("cidrs", [])
            state_set(s, "capabilities", caps)
        return caps

    def apply(self, payload):
        revision_id = payload["revision_id"]
        with self.db.session() as s:
            revision = s.get(Revision, revision_id)
            if not revision:
                raise ValueError("Revision not found")
            snapshot = revision.snapshot
            revision.status = "validating"
        caps = self.capabilities()
        if not caps.get("available"):
            raise ValueError("Agent has no running Angie binary")
        bundle = Compiler(
            self.config,
            caps,
            self.config.data_dir / "revisions" / revision_id,
            lambda obj: self.vault.decrypt(obj["encrypted_secret"]) if obj.get("encrypted_secret") else {},
        ).compile(snapshot)
        data = {"revision_id": revision_id, "configuration": bundle.config, "files": bundle.files}
        validation = self.http.post("/validate", json=data)
        if validation.is_error:
            raise ValueError(validation.json().get("detail", "Configuration validation failed"))
        with self.db.session() as s:
            s.get(Revision, revision_id).status = "applying"
        response = self.http.post("/apply", json=data)
        if response.is_error:
            detail = response.json().get("detail", "Apply failed")
            if "rollback_failed" in detail:
                with self.db.session() as s:
                    state_set(s, "apply_halted", {"halted": True, "revision_id": revision_id})
            raise ValueError(detail)
        result = response.json()
        with self.db.session() as s:
            revision = s.get(Revision, revision_id)
            revision.status = "applied"
            revision.generation = result["generation"]
            state_set(s, "applied", result)
            audit(s, "worker", "revision.applied", revision_id, generation=result["generation"])
        return result

    def execute(self, kind, payload):
        if kind == "geoip.update":
            from apm.geoip import update

            return update(self.db, self.config, payload["resource_id"])
        if kind == "apply":
            return self.apply(payload)
        if kind == "certificate.issue":
            from apm.certificates import issue

            return issue(self.db, self.config, payload["resource_id"])
        if kind == "dns.test":
            from apm.dns import provider_for

            with self.db.session() as s:
                resource = s.get(Resource, payload["resource_id"])
                provider = provider_for(self.config, resource.data, self.vault.decrypt(resource.secret or ""))
            return provider.check()
        if kind == "dns.cleanup":
            from apm.dns import provider_for

            with self.db.session() as s:
                handle = state_get(s, payload["state_key"], {})
                if not handle or handle.get("cleaned"):
                    return {"cleaned": True}
                profile = s.get(Resource, handle["profile_id"])
                if not profile:
                    raise ValueError("Challenge DNS profile was removed; local cleanup required")
                provider = provider_for(self.config, profile.data, self.vault.decrypt(profile.secret))
            provider.cleanup(handle)
            with self.db.session() as s:
                state_set(s, payload["state_key"], {**handle, "cleaned": True})
            return {"cleaned": True}
        if kind == "discovery.reconcile":
            from apm.discovery import reconcile

            return reconcile(self.db, self.config)
        if kind == "cloudflare.refresh":
            import ipaddress

            cidrs = []
            for family in ("v4", "v6"):
                response = httpx.get(f"https://www.cloudflare.com/ips-{family}", timeout=20)
                response.raise_for_status()
                cidrs += [str(ipaddress.ip_network(line)) for line in response.text.splitlines() if line]
            with self.db.session() as s:
                state_set(s, "cloudflare_cidrs", {"cidrs": cidrs, "updated_at": now()})
            return {"count": len(cidrs)}
        if kind == "ech.generate":
            from apm.ech import generate

            return generate(self.db, self.config, payload["resource_id"])
        if kind == "ech.confirm":
            from apm.ech import confirm

            return confirm(self.db, self.config, payload["resource_id"])
        if kind == "backup":
            from apm.transfers import backup

            return backup(self.db, self.config, payload["backup_id"])
        raise ValueError(f"Unknown job kind: {kind}")

    def tick(self):
        job_id = self.claim()
        if not job_id:
            return False
        with self.db.session() as s:
            row = s.get(Job, job_id)
            kind, payload = row.kind, row.payload
        try:
            result = self.execute(kind, payload)
            with self.db.session() as s:
                row = s.get(Job, job_id)
                row.status, row.result = "succeeded", result or {}
                row.updated_at = now()
        except Exception as error:
            # Do not log exception repr: HTTP errors can embed tokens and request URLs.
            logger.error("Job %s (%s) failed: %s", job_id, kind, type(error).__name__)
            message = (
                str(error)
                if isinstance(error, ValueError)
                else f"{type(error).__name__}: inspect local service diagnostics"
            )
            with self.db.session() as s:
                row = s.get(Job, job_id)
                row.status, row.error, row.updated_at = "failed", message[:1000], now()
                if kind == "apply":
                    rev = s.get(Revision, payload["revision_id"])
                    rev.status, rev.error = "failed", message[:1000]
        return True

    def run(self):
        with self.exclusive():
            self.recover()
            if self.config.discovery_enabled:
                import threading

                from apm.discovery import event_watcher

                threading.Thread(
                    target=event_watcher, args=(self.db, self.config, threading.Event()), daemon=True
                ).start()
            last_maintenance = 0
            while True:
                if time.monotonic() - last_maintenance > 60:
                    self.maintenance()
                    last_maintenance = time.monotonic()
                if not self.tick():
                    time.sleep(1)

    def maintenance(self):
        from apm.certificates import schedule_renewals

        schedule_renewals(self.db)
        if self.config.discovery_enabled:
            from apm.services import enqueue

            with self.db.session() as s:
                active = s.scalar(
                    select(Job.id).where(
                        Job.kind == "discovery.reconcile", Job.status.in_(["pending", "running"])
                    )
                )
                if not active:
                    enqueue(s, "discovery.reconcile", {})
        try:
            self.capabilities()
            status = self.http.get("/status").json()
            with self.db.session() as s:
                state_set(s, "agent_status", {**status, "collected_at": now()})
            from apm.observability import collect, rotate

            response = self.http.get("/metrics")
            if response.is_success:
                collect(self.db, response.json(), self.config.metrics_retention_days)
            rotate(self.config, self.http)
        except httpx.HTTPError:
            pass
