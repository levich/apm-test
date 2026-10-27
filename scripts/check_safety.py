"""Exercise timed safety recovery on a real, isolated Angie; no production services."""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from apm.agent import Agent, Confirmation, Deployment
from apm.compiler import Compiler
from apm.config import Settings
from apm.safety import SafetyCheck
from apm.schemas import Route, Runtime


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}' if self.path == "/health/live" else b"protected-app")

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--conf-dir", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    backend = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="safe-angie-", dir=args.work.resolve()) as temporary:
            root = Path(temporary)
            http_port, admin_port, status_port, warning_port = [free_port() for _ in range(4)]
            config = Settings(
                _env_file=None, data_dir=root, angie_binary=str(args.binary.resolve()),
                backend_url=f"http://127.0.0.1:{backend.server_port}",
                admin_listen=f"127.0.0.1:{admin_port}", public_url=f"https://localhost:{admin_port}",
                angie_status_url=f"http://127.0.0.1:{status_port}/status/angie", safe_apply_timeout=30,
            )
            agent = Agent(config)
            route = {"id": str(uuid.uuid4()), "kind": "proxy-hosts", "name": "Protected",
                     "enabled": True, "data": Route(domains=["protected.test"], host="127.0.0.1",
                                                    port=backend.server_port).model_dump()}

            def deployment(*, broken="", warning=False):
                revision = uuid.uuid4()
                resources = [route]
                if warning:
                    resources.append({"id": str(uuid.uuid4()), "kind": "runtime", "enabled": True,
                                      "data": Runtime(http_snippet=(
                                          f"server {{ listen 127.0.0.1:{warning_port}; server_name duplicate.test; }}\n"
                                          f"server {{ listen 127.0.0.1:{warning_port}; server_name duplicate.test; }}"
                                      )).model_dump()})
                bundle = Compiler(config, agent.capabilities(), root / "revisions" / str(revision)).compile(resources)
                def adapt(source):
                    source = (source.replace("user angie apm;", "")
                              .replace("listen 80", f"listen {http_port}")
                              .replace("listen [::]:80", f"listen [::]:{http_port}")
                              .replace("127.0.0.1:18081", f"127.0.0.1:{status_port}")
                              .replace("/etc/angie/mime.types", str(args.conf_dir.resolve() / "mime.types")))
                    if broken == "panel":
                        source = source.replace(f'proxy_pass "{config.backend_url}";', "return 503;")
                    if broken == "status":
                        source = source.replace("api /status/;", "return 503;")
                    return source
                files = {name: adapt(value) if name.endswith(".conf") else value
                         for name, value in bundle.files.items()}
                if broken == "host":
                    name = next(name for name in files if name.endswith(".proxy.conf"))
                    files[name] = files[name].replace("server {", "server {\nreturn 503;", 1)
                return Deployment(revision_id=revision, configuration=adapt(bundle.config), files=files,
                                  confirmation="manual", owner_id="acceptance")

            initial = deployment()
            agent.stage(initial)
            agent.switch(str(initial.revision_id))
            config.root_config.write_text(f'include "{root}/current/angie.conf";\n')
            config.safe_apply_checks = [SafetyCheck(name="Protected", scheme="http", host="127.0.0.1",
                                                    port=http_port, host_header="protected.test",
                                                    body_contains="protected-app")]
            with (root / "process.log").open("w") as log:
                process = subprocess.Popen([config.angie_binary, "-p", str(root), "-c",
                                            str(config.root_config), "-g", "daemon off;"], stdout=log, stderr=log)
                watchdog = None
                try:
                    for _ in range(50):
                        if process.poll() is not None:
                            raise AssertionError((root / "process.log").read_text())
                        try:
                            agent.generation()
                            break
                        except httpx.HTTPError:
                            time.sleep(0.1)
                    candidate = deployment(warning=True)
                    trial = agent.apply(candidate)
                    assert trial["status"] == "awaiting_confirmation" and trial["warnings"], trial
                    token = agent.safety(private=True)["token"]
                    try:
                        agent.finish_trial(Confirmation(revision_id=candidate.revision_id, token=token))
                    except ValueError as error:
                        raise AssertionError(agent.safety()) from error
                    confirmed = agent.current()
                    for broken in ("panel", "host", "status"):
                        try:
                            agent.apply(deployment(broken=broken))
                            raise AssertionError(f"Broken {broken} was accepted")
                        except ValueError as error:
                            assert "previous revision restored" in str(error), str(error)
                        assert agent.current() == confirmed
                        assert agent.safety()["status"] == "rolled_back", agent.safety()
                        # Isolated harness: no queued desired snapshots exist to cancel.
                        (root / "run/safety-halted.json").unlink()
                    # Start an independent process before the final trial. No worker or agent HTTP API runs.
                    env = {**os.environ, "APM_DATA_DIR": str(root), "APM_ANGIE_BINARY": config.angie_binary,
                           "APM_ADMIN_LISTEN": config.admin_listen, "APM_PUBLIC_URL": config.public_url,
                           "APM_ANGIE_STATUS_URL": config.angie_status_url, "APM_SAFE_APPLY_TIMEOUT": "30"}
                    watchdog = subprocess.Popen([os.sys.executable, "-c",
                                                 "from apm.cli import app; app()", "safety-watchdog"],
                                                env=env, stdout=log, stderr=log)
                    time.sleep(0.5)
                    assert watchdog.poll() is None
                    trial = agent.apply(deployment())
                    until = time.monotonic() + 45
                    while time.monotonic() < until:
                        if agent.current() == confirmed:
                            break
                        time.sleep(0.2)
                    assert agent.current() == confirmed, agent.safety()
                    assert agent.safety()["status"] == "rolled_back", agent.safety()
                    assert agent.safety()["reason"] == "timeout", agent.safety()
                    print(json.dumps({"checks": ["real Angie warning", "explicit confirmation",
                                                  "panel failure rollback", "protected host rollback",
                                                  "missing status API rollback", "independent 30-second watchdog"],
                                      "generation": agent.generation()}, indent=2))
                finally:
                    for child in (watchdog, process):
                        if child and child.poll() is None:
                            child.terminate()
                            try:
                                child.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait(timeout=5)
    finally:
        backend.shutdown()
        backend.server_close()


if __name__ == "__main__":
    main()
