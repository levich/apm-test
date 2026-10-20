"""Real existing-Angie checks with isolated data and unprivileged local ports."""

import argparse
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from apm.agent import Agent, Deployment
from apm.compiler import Compiler
from apm.config import Settings
from apm.schemas import Route, Stream


class Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"apm-existing-upstream")

    def log_message(self, *args):
        pass


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def item(kind, data):
    return {"id": str(uuid.uuid4()), "kind": kind, "enabled": True, "data": data.model_dump()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--conf-dir", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="existing-angie-", dir=args.work.resolve()) as temporary:
        root = Path(temporary)
        data = root / "data"
        http_port, status_port, stream_port = free_port(), free_port(), free_port()
        config = Settings(
            _env_file=None,
            data_dir=data,
            angie_mode="existing",
            angie_binary=str(Path(args.binary).resolve()),
            angie_config=root / "angie.conf",
            angie_prefix=root,
            angie_status_url=f"http://127.0.0.1:{status_port}/status/angie",
        )
        shutil.copyfile(args.conf_dir / "mime.types", root / "mime.types")
        legacy = root / "legacy.conf"
        legacy.write_text(
            f'server {{ listen {http_port} default_server; server_name legacy.test; return 200 "legacy"; }}\n'
        )
        # Existing main config retains its PID, HTTP defaults and relative includes.
        original = (
            f'pid "{root}/angie.pid";\nerror_log "{root}/error.log";\n'
            "events {}\nhttp {\ninclude mime.types;\ninclude legacy.conf;\n"
            "default_type text/plain; server_tokens on; ssl_protocols TLSv1.2; access_log off;\n"
            f"server {{ listen 127.0.0.1:{status_port}; location /status/ {{ api /status/; }} }}\n"
            f'include "{data}/current/http.conf";\n}}\n'
            f"stream {{\naccess_log off;\ninclude {data}/current/stream.conf;\n}}\n"
        )
        config.root_config.write_text(original)
        agent = Agent(config)
        agent.initialize()
        assert config.root_config.read_text() == original
        backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        process = subprocess.Popen(
            [config.angie_binary, "-p", str(root), "-c", str(config.root_config), "-g", "daemon off;"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode())
                try:
                    agent.generation()
                    break
                except httpx.HTTPError:
                    time.sleep(0.1)
            else:
                raise AssertionError("Existing Angie did not start")
            caps = agent.capabilities()
            assert caps["available"], caps

            def deployment(advanced=""):
                revision = uuid.uuid4()
                bundle = Compiler(config, caps, data / "revisions" / str(revision)).compile(
                    [
                        item(
                            "proxy-hosts",
                            Route(
                                domains=["managed.test"],
                                host="127.0.0.1",
                                port=backend.server_port,
                                advanced=advanced,
                            ),
                        ),
                        item(
                            "streams",
                            Stream(listen_port=stream_port, host="127.0.0.1", port=backend.server_port),
                        ),
                    ]
                )
                bundle.files["http.conf"] = (
                    bundle.files["http.conf"]
                    .replace("listen 80", f"listen {http_port}")
                    .replace("listen [::]:80", f"listen [::]:{http_port}")
                )
                return Deployment(revision_id=revision, configuration=bundle.config, files=bundle.files)

            def check_traffic():
                for domain, expected in [
                    ("legacy.test", "legacy"),
                    ("managed.test", "apm-existing-upstream"),
                ]:
                    response = httpx.get(
                        f"http://127.0.0.1:{http_port}/", headers={"Host": domain}, trust_env=False
                    )
                    assert response.status_code == 200 and response.text == expected, response.text
                response = httpx.get(f"http://127.0.0.1:{stream_port}/", trust_env=False)
                assert response.text == "apm-existing-upstream"

            candidate = deployment()
            before = agent.generation()
            result = agent.apply(candidate)
            assert result["generation"] > before
            check_traffic()
            previous = agent.current()
            for invalid_legacy in (False, True):
                if invalid_legacy:
                    legacy.write_text("apm_invalid_existing_directive on;\n")
                try:
                    agent.apply(deployment("" if invalid_legacy else "apm_invalid_directive on;"))
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid configuration was accepted")
                assert agent.current() == previous
                assert agent.generation() == result["generation"]
                check_traffic()
            assert config.root_config.read_text() == original
            assert not list(root.glob(".apm-validate-*"))
            print(
                "Existing Angie checks passed: legacy + APM HTTP, TCP, generation, rejected APM/legacy config preserves traffic and main config"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            backend.shutdown()


if __name__ == "__main__":
    main()
