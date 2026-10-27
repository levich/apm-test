"""CI smoke test for an isolated, newly installed Linux Compose deployment."""

import argparse
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


class Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"apm-compose-upstream")

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://127.0.0.1:81")
    parser.add_argument("--http-url", default="http://127.0.0.1")
    parser.add_argument("--compose-file", action="append", default=[])
    parser.add_argument("--project-name")
    parser.add_argument("--upstream-host", help="Use an existing backend reachable from Angie")
    parser.add_argument("--upstream-port", type=int, default=19080)
    args = parser.parse_args()
    compose = ["docker", "compose"]
    if args.project_name:
        compose += ["-p", args.project_name]
    for file in args.compose_file:
        compose += ["-f", file]
    server = None
    if not args.upstream_host:
        server = ThreadingHTTPServer(("0.0.0.0", args.upstream_port), Backend)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    client = httpx.Client(base_url=args.url, verify=False, trust_env=False, timeout=10)
    try:
        for attempt in range(90):
            try:
                if client.get("/health/live").is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise AssertionError("Compose manager did not become ready")
        token = subprocess.run(
            [*compose, "exec", "-T", "manager", "apm", "setup-token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout.strip()
        result = client.post(
            "/api/v1/auth/setup",
            json={"token": token, "email": "ci@example.com", "password": secrets.token_urlsafe(24)},
        )
        assert result.is_success, result.status_code
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        result = client.post(
            "/api/v1/resources/proxy-hosts",
            json={
                "name": "Compose acceptance",
                "data": {
                    "domains": ["compose.example.test"],
                    "host": args.upstream_host or "127.0.0.1",
                    "port": args.upstream_port,
                },
            },
        )
        assert result.status_code == 201, result.text
        resource = result.json()

        def wait(operation_id):
            for _ in range(60):
                job = client.get("/api/v1/operations/" + operation_id).json()
                if job["status"] == "awaiting_confirmation":
                    trial = client.get("/api/v1/safety").json()
                    confirmed = client.post("/api/v1/safety/confirm", json={
                        "revision_id": trial["revision_id"], "token": trial["token"],
                    })
                    assert confirmed.is_success, confirmed.text
                if job["status"] in ("failed", "succeeded"):
                    return job
                time.sleep(1)
            raise AssertionError("Apply operation did not finish")

        assert wait(resource["operation_id"])["status"] == "succeeded"
        response = httpx.get(args.http_url, headers={"Host": "compose.example.test"}, trust_env=False)
        assert response.text == "apm-compose-upstream"
        body = {
            "name": resource["name"],
            "data": {**resource["data"], "advanced": "apm_invalid_directive on;"},
        }
        result = client.put(
            "/api/v1/resources/proxy-hosts/" + resource["id"],
            headers={"If-Match": str(resource["version"])},
            json=body,
        )
        assert result.is_success, (result.status_code, result.text)
        assert wait(result.json()["operation_id"])["status"] == "failed"
        assert (
            httpx.get(args.http_url, headers={"Host": "compose.example.test"}, trust_env=False).text
            == "apm-compose-upstream"
        )
        print(
            "Compose smoke test passed: setup, API/worker/UDS agent, real HTTP, rejected configuration preserves traffic"
        )
    finally:
        if server:
            server.shutdown()
        client.close()


if __name__ == "__main__":
    main()
