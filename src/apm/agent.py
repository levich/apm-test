import fcntl
import ipaddress
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from apm.compiler import Compiler, q
from apm.config import Settings
from apm.safety import SafetyCheck, check_routes, warnings
from apm.security import atomic_write, digest


def bootstrap_certificate(config):
    directory = config.data_dir / "bootstrap"
    directory.mkdir(exist_ok=True, mode=0o750)
    if (directory / "fullchain.pem").exists() and (directory / "privkey.pem").exists():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Angie Proxy Manager setup")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=5))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            False,
        )
        .sign(key, hashes.SHA256())
    )
    atomic_write(
        directory / "privkey.pem",
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
        0o640,
    )
    atomic_write(directory / "fullchain.pem", cert.public_bytes(serialization.Encoding.PEM), 0o640)


class Deployment(BaseModel):
    revision_id: uuid.UUID
    configuration: str = Field(max_length=2_000_000)
    files: dict[str, str] = {}
    confirmation: Literal["manual", "automatic"] = "automatic"
    owner_id: str = ""
    owner_session: str = ""


class SafetyConflict(ValueError):
    pass


class Confirmation(BaseModel):
    revision_id: uuid.UUID
    token: str = Field(min_length=20, max_length=128)


class AngieCommandError(ValueError):
    def __init__(self, code, output):
        super().__init__(f"Angie command failed (exit {code}); inspect the local error log")
        self.warnings = warnings(output)


class Agent:
    def __init__(self, config: Settings):
        self.config = config
        config.prepare()
        bootstrap_certificate(config)

    @contextmanager
    def lock(self):
        with (self.config.data_dir / "run/apply.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def command(self, *args):
        result = subprocess.run(
            [self.config.angie_binary, "-p", str(self.config.angie_prefix or self.config.data_dir), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            # Configuration diagnostics can contain credentials. Do not persist stderr.
            raise AngieCommandError(result.returncode, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def capabilities(self):
        try:
            version = self.command("-V")
            modules = self.command("-m")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return {"available": False, "reason": "Angie binary not available"}
        module_paths = []
        desired = (
            "stream",
            "ndk_http",
            "http_lua",
            "stream_lua",
            "http_brotli_filter",
            "http_brotli_static",
            "http_zstd_filter",
            "http_zstd_static",
            "http_headers_more_filter",
            "http_geoip2",
            "http_fancyindex",
        )
        for name in desired:
            for directory in ("/usr/lib/angie/modules", "/etc/angie/modules", "/usr/lib64/angie/modules"):
                path = Path(directory) / (
                    "ndk_http_module.so" if name == "ndk_http" else f"ngx_{name}_module.so"
                )
                if path.exists():
                    module_paths.append(str(path.resolve()))
                    break
        joined = version + modules + " ".join(module_paths)
        caps = {
            "available": True,
            "version": next(
                (line for line in version.splitlines() if line.startswith("Angie version:")), "Angie"
            ),
            "edition": "pro" if "(PRO)" in version or "Angie PRO" in version else "oss",
            "module_paths": module_paths,
        }
        for feature, marker in {
            "grpc": "grpc",
            "http3": "v3",
            "brotli": "brotli",
            "zstd": "zstd",
            "headers_more": "headers_more",
            "geoip2": "geoip2",
            "fancyindex": "fancyindex",
        }.items():
            caps[feature] = {"supported": marker in joined, "verification": "module-discovery"}
        caps["quic_bpf"] = {
            "supported": False,
            "reason": "Requires privileged Linux extended profile validation",
        }
        import socket
        import sys

        try:
            if sys.platform != "linux":
                raise OSError("Linux required")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 262):
                pass
            caps["mptcp"] = {
                "supported": True,
                "verification": "kernel MPTCP socket probe; candidate additionally validated by angie -t",
            }
        except OSError:
            caps["mptcp"] = {"supported": False, "reason": "Kernel does not permit an MPTCP TCP socket"}
        for feature in ("ech", "certificate_compression"):
            cert = self.config.data_dir / "bootstrap"
            directive = (
                f"ssl_encrypted_hello_key {q(self.config.data_dir / 'ech/probe.pem')};"
                if feature == "ech"
                else "ssl_certificate_compression on;"
            )
            # ECH must have a valid key to prove support; an ignored directive is not support.
            if feature == "ech" and not (self.config.data_dir / "ech/probe.pem").exists():
                from apm.ech import key_pair

                pem, _ = key_pair("probe.example.com")
                atomic_write(self.config.data_dir / "ech/probe.pem", pem, 0o640)
            probe = self.config.data_dir / "run" / f"probe-{feature}.conf"
            probe.write_text(
                f"events {{}} http {{ server {{ listen 127.0.0.1:19819 ssl; ssl_certificate {q(cert / 'fullchain.pem')}; ssl_certificate_key {q(cert / 'privkey.pem')}; {directive} }} }}"
            )
            try:
                output = self.command("-t", "-c", str(probe))
                supported = not any(
                    token in output.lower() for token in ("ignored", "not supported", "unknown directive")
                )
            except (OSError, ValueError):
                supported = False
            finally:
                probe.unlink(missing_ok=True)
            caps[feature] = {"supported": supported, "verification": "syntax-probe"}
        caps["crowdsec"] = {
            "supported": Path("/opt/apm/lua/access.lua").exists() and "http_lua" in joined,
            "verification": "module-discovery",
        }
        return caps

    def generation(self):
        response = httpx.get(self.config.angie_status_url, timeout=2, trust_env=False)
        response.raise_for_status()
        return int(response.json()["generation"])

    def switch(self, revision_id):
        target = self.config.data_dir / "revisions" / revision_id
        if not target.is_dir() or target.is_symlink():
            raise ValueError("Revision does not exist")
        link = self.config.data_dir / "current"
        tmp = self.config.data_dir / f".current-{uuid.uuid4().hex}"
        tmp.symlink_to(target)
        os.replace(tmp, link)
        directory_fd = os.open(self.config.data_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def current(self):
        path = self.config.data_dir / "current"
        return path.resolve().name if path.is_symlink() else None

    def stage(self, deployment: Deployment):
        rid = str(deployment.revision_id)
        directory = self.config.data_dir / "revisions" / rid
        # Keep the original bundle hash independent of confirmation/session metadata.
        payload_hash = digest(json.dumps(deployment.model_dump(
            mode="json", include={"revision_id", "configuration", "files"}
        ), sort_keys=True))
        if directory.exists():
            if (directory / "manifest.json").exists() and json.loads(
                (directory / "manifest.json").read_text()
            )["hash"] == payload_hash:
                return directory
            raise ValueError("Revision is immutable")
        directory.mkdir(mode=0o750)
        try:
            for name, contents in deployment.files.items():
                relative = Path(name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                ):
                    raise ValueError("Invalid bundle path")
                if name in ("angie.conf", "manifest.json"):
                    raise ValueError("Reserved bundle path")
                atomic_write(directory / relative, contents.encode(), 0o640)
            atomic_write(directory / "angie.conf", deployment.configuration.encode(), 0o640)
            atomic_write(
                directory / "manifest.json", json.dumps({"id": rid, "hash": payload_hash}).encode(), 0o640
            )
        except Exception:
            import shutil

            shutil.rmtree(directory)
            raise
        return directory

    def initialize(self):
        with self.lock():
            # Cold boot must start Angie with the confirmed files, never a pending candidate.
            journal = self.config.data_dir / "run/apply-journal.json"
            if journal.exists():
                state = json.loads(journal.read_text())
                receipt = self.read_json("receipt.json", {})
                if receipt.get("revision_id") == state.get("candidate") and self.current() == state["candidate"]:
                    journal.unlink()
                else:
                    if state.get("previous"):
                        self.switch(state["previous"])
                    state.update(status="rolling_back", reason="restart")
                    self.write_journal(state)
            if self.config.angie_mode == "existing":
                if not self.config.root_config.is_file():
                    raise ValueError("Existing Angie configuration does not exist")
                if not self.current():
                    rid = str(uuid.uuid4())
                    bundle = Compiler(self.config, {}, self.config.data_dir / "revisions" / rid).compile([])
                    self.stage(Deployment(revision_id=rid, configuration=bundle.config, files=bundle.files))
                    self.switch(rid)
                return
            if not self.config.root_config.exists():
                rid = str(uuid.uuid4())
                bundle = Compiler(
                    self.config, self.capabilities(), self.config.data_dir / "revisions" / rid
                ).compile([])
                self.stage(Deployment(revision_id=rid, configuration=bundle.config, files=bundle.files))
                self.switch(rid)
                atomic_write(
                    self.config.root_config,
                    f"include {q(self.config.data_dir / 'current/angie.conf')};\n".encode(),
                    0o640,
                )

    def validate(self, directory):
        if self.config.angie_mode != "existing":
            return warnings(self.command("-t", "-c", str(directory / "angie.conf")))
        source = self.config.root_config.read_text()
        for name in ("http.conf", "stream.conf"):
            if not (directory / name).is_file():
                raise ValueError(f"Existing Angie bundle requires {name}")
            current = self.config.data_dir / "current" / name
            # Explicit, standalone includes in the root file keep validation independent
            # of current and preserve relative includes in the administrator's config.
            pattern = (
                r'(?m)^(\s*include\s+)(?:"'
                + re.escape(str(current))
                + r'"|'
                + re.escape(str(current))
                + r")(\s*;[^\n]*)$"
            )
            source, count = re.subn(pattern, lambda m: m[1] + q(directory / name) + m[2], source)
            if count != 1:
                raise ValueError(f"Add exactly one standalone include {current}; to APM_ANGIE_CONFIG")
        # Angie resolves relative includes against the main file's directory.
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=".apm-validate-", suffix=".conf", dir=self.config.root_config.parent
        ) as candidate:
            candidate.write(source)
            candidate.flush()
            return warnings(self.command("-t", "-c", candidate.name))

    def reload(self, before):
        self.command("-s", "reload", "-c", str(self.config.root_config))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                generation = self.generation()
                if before is None or generation > before:
                    # Successful HTTP status confirms that new workers serve requests.
                    return generation
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
        raise ValueError("Reload was not confirmed by the status API")

    def read_json(self, name, default=None):
        path = self.config.data_dir / "run" / name
        return json.loads(path.read_text()) if path.exists() else default

    def write_journal(self, state):
        atomic_write(self.config.data_dir / "run/apply-journal.json", json.dumps(state).encode())

    def public_state(self, state):
        return {k: v for k, v in state.items()
                if k not in ("token", "owner_id", "owner_session", "plans", "deadline_monotonic")}

    def record(self, state):
        public = self.public_state(state)
        atomic_write(self.config.data_dir / "run/safety-status.json", json.dumps(public).encode(), 0o640)
        atomic_write(
            self.config.data_dir / "run/receipts" / (state["revision_id"] + ".json"),
            json.dumps(public).encode(), 0o640,
        )
        return public

    def safety(self, private=False):
        with self.lock():
            state = self.read_json("apply-journal.json") or self.read_json("safety-status.json", {})
            result = dict(state) if private else self.public_state(state)
            result["halted"] = bool(self.read_json("safety-halted.json"))
            result["active_revision"] = self.current()
            result["confirmed"] = self.read_json("receipt.json", {})
            result["seconds_remaining"] = max(0, int(min(
                state.get("deadline", 0) - time.time(),
                state.get("deadline_monotonic", float("inf")) - time.monotonic(),
            )))
            return result

    def plans(self, revision_id):
        checks = list(self.config.safe_apply_checks)
        public = urlsplit(self.config.public_url)
        if self.config.angie_mode == "managed":
            host, port = self.config.admin_listen.rsplit(":", 1)
            host = host.strip("[]")
            host = "127.0.0.1" if host in ("", "*", "0.0.0.0") else "::1" if host == "::" else host
            panel = SafetyCheck(
                name="APM", host=host, port=int(port), path="/health/live",
                server_name="localhost", host_header=public.netloc or "localhost",
                ca_file=str(self.config.data_dir / "bootstrap/fullchain.pem"),
                body_contains='"status":"ok"', revision=revision_id,
            )
        else:
            panel = SafetyCheck(
                name="APM", scheme=public.scheme, host=public.hostname or "localhost",
                port=public.port or (443 if public.scheme == "https" else 80),
                path=public.path.rstrip("/") + "/health/live", body_contains='"status":"ok"',
            )
        return [panel, *checks]

    def run_checks(self, state, attempts=1):
        plans = [SafetyCheck.model_validate(check) for check in state.get("plans", [])]
        return self.probe_plans(plans, attempts)

    def probe_plans(self, plans, attempts=1):
        for attempt in range(attempts):
            checks = check_routes(plans)
            if all(check["ok"] for check in checks):
                return checks
            if attempt + 1 < attempts:
                time.sleep(0.2)
        return checks

    def expired(self, state):
        return (time.time() >= state.get("deadline", 0)
                or time.monotonic() >= state.get("deadline_monotonic", float("inf")))

    def commit(self, state):
        state["status"] = "applied"
        result = self.record(state)
        atomic_write(self.config.data_dir / "run/receipt.json", json.dumps(result).encode(), 0o640)
        (self.config.data_dir / "run/apply-journal.json").unlink(missing_ok=True)
        return result

    def rollback(self, state, reason):
        state.update(status="rolling_back", reason=reason)
        self.write_journal(state)
        # Halt independently of SQLite/worker availability, before any recovery commands.
        atomic_write(self.config.data_dir / "run/safety-halted.json", b'{"halted":true}', 0o640)
        try:
            previous = state.get("previous")
            if not previous:
                raise ValueError("No confirmed revision is available")
            self.switch(previous)
            self.validate(self.config.data_dir / "revisions" / previous)
            try:
                before = self.generation()
            except Exception:
                before = None
            state["rollback_generation"] = self.reload(before)
            if self.config.safe_apply:
                plans = [SafetyCheck.model_validate({
                    **p, "revision": previous if p.get("revision") and state.get("previous_has_marker") else "",
                }) for p in state.get("plans", [])]
                state["rollback_checks"] = self.probe_plans(plans, attempts=3)
                if not all(check["ok"] for check in state["rollback_checks"]):
                    raise ValueError("Recovery route checks failed")
            state["status"] = "rolled_back"
            result = self.record(state)
            (self.config.data_dir / "run/apply-journal.json").unlink(missing_ok=True)
            return result
        except Exception as error:
            state["status"] = "rollback_failed"
            self.write_journal(state)
            self.record(state)
            raise RuntimeError("rollback_failed: further applies require local recovery") from error

    def recover(self):
        # Caller holds the apply lock. Used on agent/watchdog restart, not every apply.
        state = self.read_json("apply-journal.json")
        if state:
            state.setdefault("revision_id", state["candidate"])
            # A durable receipt wins over an interrupted journal cleanup after commit.
            receipt = self.read_json("receipt.json", {})
            if receipt.get("revision_id") == state["revision_id"] and self.current() == state["revision_id"]:
                (self.config.data_dir / "run/apply-journal.json").unlink(missing_ok=True)
                return
            return self.rollback(state, "restart")

    def watchdog_tick(self):
        with self.lock():
            state = self.read_json("apply-journal.json")
            if not state or state.get("status") == "rollback_failed":
                return
            if self.expired(state) or state.get("status") == "rolling_back":
                return self.rollback(state, state.get("reason", "timeout"))
            checks = self.run_checks(state)
            state["checks"] = checks
            if not all(item["ok"] for item in checks):
                state["failures"] = state.get("failures", 0) + 1
                if state["failures"] >= 3:
                    return self.rollback(state, "health_failed")
            else:
                state["failures"] = 0
            self.write_journal(state)

    def watch(self, stop):
        while not stop.wait(2):
            try:
                self.watchdog_tick()
            except Exception:
                # The durable journal is the diagnostic source; never log raw commands.
                pass

    def finish_trial(self, confirmation, rollback=False):
        with self.lock():
            state = self.read_json("apply-journal.json")
            rid = str(confirmation.revision_id)
            if not state or state.get("revision_id") != rid:
                raise SafetyConflict("This revision is no longer awaiting confirmation")
            if not secrets.compare_digest(state.get("token", ""), confirmation.token):
                raise SafetyConflict("Invalid confirmation token")
            if rollback:
                return self.rollback(state, "cancelled")
            if state.get("status") != "awaiting_confirmation" or self.expired(state):
                self.rollback(state, "timeout")
                raise SafetyConflict("The confirmation deadline has expired")
            checks = self.run_checks(state, attempts=3)
            state["checks"] = checks
            self.write_journal(state)
            if not all(item["ok"] for item in checks):
                raise SafetyConflict("Required route checks have not passed")
            if self.expired(state):
                self.rollback(state, "timeout")
                raise SafetyConflict("The confirmation deadline has expired")
            return self.commit(state)

    def apply(self, deployment: Deployment):
        with self.lock():
            rid = str(deployment.revision_id)
            pending = self.read_json("apply-journal.json")
            if pending:
                if pending.get("revision_id") == rid:
                    self.stage(deployment)
                    return self.public_state(pending)
                raise SafetyConflict("Another revision is awaiting confirmation or recovery")
            existing = self.read_json("receipts/" + rid + ".json")
            if existing:
                self.stage(deployment)
                return {**existing, "active_revision": self.current()}
            if self.read_json("safety-halted.json"):
                raise SafetyConflict("Applies are halted; inspect safety status and run apm resume-applies")
            directory = self.stage(deployment)
            receipt = self.config.data_dir / "run/receipt.json"
            if receipt.exists():
                existing = json.loads(receipt.read_text())
                if existing["revision_id"] == rid and self.current() == rid:
                    return existing
            diagnostics = self.validate(directory)
            if self.config.angie_mode == "existing" and not self.current():
                raise ValueError("Run apm bootstrap-agent before applying to an existing Angie")
            before = self.generation()
            previous = self.current()
            plans = self.plans(rid) if self.config.safe_apply else []
            # Establish the contract before activation; a pre-existing failure is not a regression.
            baseline = check_routes([p.model_copy(update={"revision": ""}) for p in plans])
            required = {item["name"] for item in baseline if item["ok"]}
            plans = [p for p in plans if p.name == "APM" or p.name in required]
            if self.config.safe_apply and deployment.confirmation == "automatic" and not all(
                item["ok"] for item in baseline
            ):
                raise SafetyConflict("Required route checks must pass before automatic apply")
            state = {
                "revision_id": rid, "candidate": rid, "previous": previous,
                "previous_revision_id": previous, "status": "applying", "warnings": diagnostics,
                "previous_has_marker": bool(previous and "add_header X-APM-Revision " in (
                    self.config.data_dir / "revisions" / previous / "angie.conf"
                ).read_text()),
                "started_at": time.time(), "deadline": time.time() + self.config.safe_apply_timeout,
                "deadline_monotonic": time.monotonic() + self.config.safe_apply_timeout,
                "plans": [p.model_dump() for p in plans], "baseline": baseline,
                "token": secrets.token_urlsafe(32), "owner_id": deployment.owner_id,
                "owner_session": deployment.owner_session,
            }
            self.write_journal(state)
            try:
                self.switch(rid)
                generation = self.reload(before)
                state["generation"] = generation
                checks = self.run_checks(state, attempts=3)
                state["checks"] = checks
                if not all(item["ok"] for item in checks):
                    raise ValueError("Required route checks failed")
                if self.expired(state):
                    raise ValueError("The confirmation deadline has expired")
            except Exception as original:
                self.rollback(state, "activation_failed")
                raise ValueError("Candidate was not activated; previous revision restored") from original
            if self.config.safe_apply and deployment.confirmation == "manual":
                state["status"] = "awaiting_confirmation"
                self.write_journal(state)
                return self.public_state(state)
            return self.commit(state)


def create_agent(config=None):
    config = config or Settings()
    agent = Agent(config)

    @asynccontextmanager
    async def lifespan(app):
        with (config.data_dir / "run/maintenance.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            with agent.lock():
                try:
                    agent.recover()
                except RuntimeError:
                    pass
            stop = threading.Event()
            watchdog = threading.Thread(target=agent.watch, args=(stop,), daemon=True)
            watchdog.start()
            try:
                yield
            finally:
                stop.set()
                watchdog.join(timeout=5)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic's default error response can echo the entire private bundle/token.
        return JSONResponse({"detail": "Invalid agent request"}, status_code=422)

    @app.get("/capabilities")
    def capabilities():
        return agent.capabilities()

    @app.get("/status")
    def status():
        try:
            return {"active_revision": agent.current(), "generation": agent.generation(), "available": True}
        except Exception:
            return {"active_revision": agent.current(), "available": False}

    @app.post("/validate")
    def validate(data: Deployment):
        try:
            with agent.lock():
                directory = agent.stage(data)
                diagnostics = agent.validate(directory)
            return {"valid": True, "warnings": diagnostics}
        except Exception as error:
            return JSONResponse({"detail": str(error), "warnings": getattr(error, "warnings", [])}, status_code=422)

    @app.get("/safety")
    def safety():
        return agent.safety(private=True)

    @app.post("/safety/confirm")
    def confirm_trial(data: Confirmation):
        try:
            return agent.finish_trial(data)
        except SafetyConflict as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/safety/rollback")
    def rollback_trial(data: Confirmation):
        try:
            return agent.finish_trial(data, rollback=True)
        except SafetyConflict as error:
            raise HTTPException(409, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @app.get("/metrics")
    def metrics():
        url = config.angie_status_url.rsplit("/angie", 1)[0] + "/"
        response = httpx.get(url, timeout=5, trust_env=False)
        response.raise_for_status()
        return response.json()

    from apm.health import CheckRequest, check

    @app.post("/backend-health")
    def backend_health(data: CheckRequest):
        return {"checks": check(data.targets)}

    @app.post("/logs/reopen")
    def reopen_logs():
        agent.command("-s", "reopen", "-c", str(config.root_config))
        return {"ok": True}

    @app.post("/apply")
    def apply(data: Deployment):
        try:
            return agent.apply(data)
        except SafetyConflict as error:
            raise HTTPException(409, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:
            raise HTTPException(422, str(error)) from error

    return app
