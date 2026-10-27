"""Real Angie + simulated outpost: anonymous request -> sign-in -> callback -> cookie -> app."""

import argparse
import json
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from apm.compiler import Compiler
from apm.config import Settings
from apm.schemas import AuthProvider, Headers, Route


class Outpost(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        assert self.request_version == "HTTP/1.1"
        assert self.headers.get("X-Forwarded-Host", "").startswith("application.test")
        if path == "/outpost.goauthentik.io/auth/nginx":
            authorized = "ak_session=valid" in self.headers.get("Cookie", "")
            self.send_response(204 if authorized else 401)
            self.send_header("Set-Cookie", "ak_refresh=received; Path=/; HttpOnly")
            if authorized:
                self.send_header("X-Authentik-Username", "alice")
        elif path == "/outpost.goauthentik.io/start":
            self.send_response(302)
            self.send_header("Location", "/outpost.goauthentik.io/callback?code=synthetic-code")
        elif path == "/outpost.goauthentik.io/callback":
            self.send_response(302)
            self.send_header("Set-Cookie", "ak_session=valid; Path=/; HttpOnly")
            self.send_header("Location", "/")
        else:
            self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


class Application(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(("application:" + self.headers.get("X-Authentik-Username", "missing")).encode())

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), handler) for handler in (Outpost, Application)]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    resolver = socket.getaddrinfo
    def resolve(host, *args, **kwargs):
        return resolver("127.0.0.1" if host in ("application.test", b"application.test") else host, *args, **kwargs)
    socket.getaddrinfo = resolve
    try:
        with tempfile.TemporaryDirectory(prefix="authentik-", dir=args.work.resolve()) as temporary:
            root = Path(temporary)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = Settings(_env_file=None, data_dir=root)
            provider_id, header_id = str(uuid.uuid4()), str(uuid.uuid4())
            provider = AuthProvider(provider="authentik", url=f"http://127.0.0.1:{servers[0].server_port}",
                                    identity_headers=["X-Authentik-Username"])
            resources = [
                {"id": provider_id, "kind": "auth-providers", "data": provider.model_dump()},
                {"id": header_id, "kind": "header-policies", "data": Headers(hsts=True).model_dump()},
                {"id": str(uuid.uuid4()), "kind": "proxy-hosts", "name": "application",
                 "data": Route(domains=["application.test"], host="127.0.0.1", port=servers[1].server_port,
                               auth_provider_id=provider_id, header_policy_id=header_id).model_dump()},
            ]
            bundle = Compiler(config, {}, root / "revisions" / str(uuid.uuid4())).compile(resources)
            fragment = next(value for name, value in bundle.files.items() if name.endswith(".proxy.conf"))
            fragment = fragment.replace("listen 80;", f"listen 127.0.0.1:{port};").replace("listen [::]:80;", "")
            source = (f'pid "{root}/angie.pid"; error_log "{root}/error.log";\nevents {{}}\nhttp {{\n'
                      "variables_hash_bucket_size 64;\naccess_log off;\n"
                      "map $http_upgrade $apm_connection { default upgrade; '' close; }\n"
                      "map $http_host $apm_original_host { default $http_host; '' $host; }\n"
                      + fragment + "\n}\n")
            path = root / "angie.conf"
            path.write_text(source)
            process = subprocess.Popen([args.binary, "-e", "stderr", "-p", str(root), "-c", str(path),
                                        "-g", "daemon off;"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                with httpx.Client(base_url=f"http://application.test:{port}",
                                  trust_env=False, timeout=5) as client:
                    for _ in range(50):
                        if process.poll() is not None:
                            raise AssertionError(process.stderr.read().decode())
                        try:
                            response = client.get("/")
                            break
                        except httpx.ConnectError:
                            time.sleep(0.1)
                    else:
                        raise AssertionError("Angie did not start")
                    assert response.status_code == 302, response.status_code
                    location = response.headers["location"]
                    assert urlsplit(location).path == "/outpost.goauthentik.io/start", location
                    assert parse_qs(urlsplit(location).query)["rd"] == [f"http://application.test:{port}/"], location
                    assert "ak_refresh=received" in response.headers.get("set-cookie", ""), response.headers
                    assert "Strict-Transport-Security" in response.headers
                    # The simulated callback grants only a test cookie; no real credentials are used.
                    response = client.get(location, follow_redirects=True,
                                          headers={"X-Authentik-Username": "forged-client-identity"})
                    assert response.status_code == 200 and response.text == "application:alice", response.text
                    assert "Strict-Transport-Security" in response.headers
                    assert client.cookies.get("ak_session") == "valid"
                    print(json.dumps({"checks": ["anonymous 302", "NAS-local start URL with return target",
                                                  "auth cookie forwarded on redirect", "public callback",
                                                  "session cookie reaches authorization subrequest",
                                                  "identity header cannot be forged", "HSTS retained",
                                                  "Linux variables hash bucket 64"]}, indent=2))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    finally:
        socket.getaddrinfo = resolver
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
