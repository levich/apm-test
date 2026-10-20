import fcntl
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from apm.compiler import Compiler, q
from apm.config import Settings
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
            raise ValueError(f"Angie command failed (exit {result.returncode}); inspect the local error log")
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

    def current(self):
        path = self.config.data_dir / "current"
        return path.resolve().name if path.is_symlink() else None

    def stage(self, deployment: Deployment):
        rid = str(deployment.revision_id)
        directory = self.config.data_dir / "revisions" / rid
        payload_hash = digest(json.dumps(deployment.model_dump(mode="json"), sort_keys=True))
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
            self.command("-t", "-c", str(directory / "angie.conf"))
            return
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
            self.command("-t", "-c", candidate.name)

    def reload(self, before):
        self.command("-s", "reload", "-c", str(self.config.root_config))
        for _ in range(50):
            try:
                generation = self.generation()
                if generation > before:
                    # Successful HTTP status confirms that new workers serve requests.
                    return generation
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
        raise ValueError("Reload was not confirmed by the status API")

    def recover(self):
        journal = self.config.data_dir / "run/apply-journal.json"
        if not journal.exists():
            return
        state = json.loads(journal.read_text())
        previous = state.get("previous")
        if previous:
            before = self.generation()
            self.switch(previous)
            self.reload(before)
        journal.unlink()

    def apply(self, deployment: Deployment):
        with self.lock():
            self.recover()
            directory = self.stage(deployment)
            rid = str(deployment.revision_id)
            receipt = self.config.data_dir / "run/receipt.json"
            if receipt.exists():
                existing = json.loads(receipt.read_text())
                if existing["revision_id"] == rid and self.current() == rid:
                    return existing
            self.validate(directory)
            if self.config.angie_mode == "existing" and not self.current():
                raise ValueError("Run apm bootstrap-agent before applying to an existing Angie")
            before = self.generation()
            previous = self.current()
            journal = self.config.data_dir / "run/apply-journal.json"
            atomic_write(journal, json.dumps({"previous": previous, "candidate": rid}).encode())
            try:
                self.switch(rid)
                generation = self.reload(before)
            except Exception as original:
                try:
                    if previous:
                        current_generation = self.generation()
                        self.switch(previous)
                        self.reload(current_generation)
                    journal.unlink(missing_ok=True)
                except Exception as rollback:
                    raise RuntimeError(
                        "rollback_failed: further applies require local recovery"
                    ) from rollback
                raise ValueError("Candidate was not activated; previous revision restored") from original
            result = {"revision_id": rid, "previous_revision_id": previous, "generation": generation}
            atomic_write(receipt, json.dumps(result).encode(), 0o640)
            journal.unlink(missing_ok=True)
            return result


def create_agent(config=None):
    config = config or Settings()
    agent = Agent(config)

    @asynccontextmanager
    async def lifespan(app):
        with (config.data_dir / "run/maintenance.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

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
                agent.validate(directory)
            return {"valid": True}
        except Exception as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/metrics")
    def metrics():
        url = config.angie_status_url.rsplit("/angie", 1)[0] + "/"
        response = httpx.get(url, timeout=5, trust_env=False)
        response.raise_for_status()
        return response.json()

    @app.post("/logs/reopen")
    def reopen_logs():
        agent.command("-s", "reopen", "-c", str(config.root_config))
        return {"ok": True}

    @app.post("/apply")
    def apply(data: Deployment):
        try:
            return agent.apply(data)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:
            raise HTTPException(422, str(error)) from error

    return app
