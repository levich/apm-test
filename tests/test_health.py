import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from apm import health
from apm.agent import create_agent
from apm.db import Database, Resource, now, state_get
from apm.schemas import Route, Upstream
from apm.services import serialize
from apm.worker import Worker


@pytest.fixture
def backend():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers["Host"]))
            code = int(self.path.lstrip("/") or "200")
            self.send_response(code)
            if code == 302:
                self.send_header("Location", "/500")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, requests
    server.shutdown()
    server.server_close()
    thread.join()


def target(port, **changes):
    return health.Target(
        resource_id="route",
        host="127.0.0.1",
        port=port,
        scheme="http",
        host_header="app.example.com",
        sni="app.example.com",
        **changes,
    )


@pytest.mark.parametrize("code,expected", [(200, "up"), (302, "up"), (401, "up"), (404, "up"), (503, "down")])
def test_http_probe_checks_status_host_and_does_not_follow_redirects(backend, code, expected):
    port, requests = backend
    result = health.probe(target(port, path=f"/{code}"))
    assert result["status"] == expected
    assert result["http_status"] == code
    assert requests == [(f"/{code}", "app.example.com")]


@pytest.mark.parametrize(
    "error,reason",
    [
        (socket.gaierror(), "dns_error"),
        (TimeoutError(), "timeout"),
        (ConnectionRefusedError(), "connection_error"),
        (ssl.SSLCertVerificationError(), "tls_error"),
    ],
)
def test_probe_reports_safe_failures(monkeypatch, error, reason):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(health.socket, "create_connection", fail)
    assert health.probe(target(80))["reason"] == reason


def test_tls_probe_uses_configured_sni_and_verification(monkeypatch):
    class Socket:
        def settimeout(self, timeout):
            assert 0 < timeout <= 3

        def close(self):
            pass

    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def wrap_socket(self, sock, server_hostname):
            assert server_hostname == "app.example.com"
            assert self.verify_mode == ssl.CERT_NONE
            assert self.check_hostname is False
            return sock

    monkeypatch.setattr(health.socket, "create_connection", lambda *args: Socket())
    monkeypatch.setattr(health.ssl, "create_default_context", Context)
    data = target(443).model_copy(update={"scheme": "grpcs", "verify": False})
    assert health.probe(data)["reason"] == "tls_connected"


def test_plans_include_locations_backup_and_invalidate_changed_targets():
    group = {
        "id": "pool",
        "kind": "upstreams",
        "enabled": True,
        "data": Upstream(
            peers=[
                {"host": "one.example.com"},
                {"host": "two.example.com", "backup": True},
                {"host": "three.example.com", "down": True},
            ]
        ).model_dump(),
    }
    route = {
        "id": "route",
        "kind": "proxy-hosts",
        "enabled": True,
        "data": Route(
            domains=["app.example.com"],
            upstream_id="pool",
            locations=[{"path": "/api", "strip_prefix": True}],
        ).model_dump(),
    }
    plan = health.plans([route, group])["route"]
    assert len(plan["targets"]) == 3
    assert plan["targets"][1]["backup"] is True
    assert plan["targets"][2]["route_path"] == "/api"
    assert plan["targets"][2]["path"] == "/"
    group["data"]["peers"][0]["host"] = "new.example.com"
    assert health.plans([route, group])["route"]["signature"] != plan["signature"]


def test_agent_check_collect_cache_staleness_and_disabled(admin, config, backend, monkeypatch):
    port, _ = backend
    route = admin.post(
        "/api/v1/resources/proxy-hosts",
        json={
            "name": "test",
            "data": {"domains": ["app.example.com"], "host": "127.0.0.1", "port": port},
        },
    ).json()
    database = admin.app.state.db
    with TestClient(create_agent(config)) as agent:
        health.collect(database, agent)
    item = admin.get("/api/v1/resources/proxy-hosts").json()[0]
    assert item["health"]["status"] == "up"
    assert "health" not in item["data"]
    with database.session() as session:
        obj = session.get(Resource, route["id"])
        plan = health.plans([serialize(obj)])[obj.id]
        assert "health" not in serialize(obj)
        cached = state_get(session, "backend-health:" + obj.id)
        monkeypatch.setattr(health, "now", lambda: cached["checked_at"] + 91)
        assert health.summary(session, obj, plan)["status"] == "unknown"
        obj.enabled = False
        assert health.summary(session, obj, plan)["status"] == "disabled"


def test_partial_aggregation_and_parallel_limit(monkeypatch):
    assert health.aggregate([{"status": "up"}, {"status": "down"}]) == "partial"
    assert health.aggregate([]) == "down"
    active = peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def probe(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 8:
                release.set()
        assert release.wait(2)
        with lock:
            active -= 1
        return {"status": "up"}

    monkeypatch.setattr(health, "probe", probe)
    assert len(health.check([target(80)] * 24)) == 24
    assert peak == 8


def test_worker_monitor_continues_during_busy_queue(config, monkeypatch):
    database = Database(config)
    database.initialize()
    worker = Worker(config, database)
    busy, observed = threading.Event(), threading.Event()

    def collect(*args):
        assert busy.wait(2)
        observed.set()

    def long_job():
        busy.set()
        assert observed.wait(2), "monitor was blocked by the queue"
        raise KeyboardInterrupt

    monkeypatch.setattr(health, "collect", collect)
    monkeypatch.setattr(worker, "maintenance", lambda: None)
    monkeypatch.setattr(worker, "tick", long_job)
    with pytest.raises(KeyboardInterrupt):
        worker.run()
    worker.http.close()


def test_monitor_http_failure_does_not_modify_configuration(admin):
    database = admin.app.state.db
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503)), base_url="http://agent"
    )
    admin.post("/api/v1/resources/proxy-hosts", json={"name": "host", "data": {"domains": ["example.com"]}})
    with pytest.raises(httpx.HTTPStatusError):
        health.collect(database, client)
    item = admin.get("/api/v1/resources/proxy-hosts").json()[0]
    assert item["version"] == 1
    assert item["health"]["status"] == "unknown"
    assert now() > 0


def test_empty_upstream_and_invalid_settings_are_reported_without_breaking_lists(admin, config):
    route = admin.post(
        "/api/v1/resources/proxy-hosts",
        json={
            "name": "invalid check",
            "data": {"domains": ["example.com"], "upstream_sni": "not a TLS name"},
        },
    )
    assert route.status_code == 201
    item = admin.get("/api/v1/resources/proxy-hosts").json()[0]
    assert item["health"]["status"] == "unknown"
    plan = health.plans([item])[item["id"]]
    assert not plan["targets"]
    assert plan["errors"][0]["reason"] == "invalid_target"
    item["data"]["upstream_sni"] = None
    item["data"]["upstream_id"] = "removed-upstream"
    plan = health.plans([item])[item["id"]]
    assert plan["errors"][0]["reason"] == "no_peers"
    item["data"]["locations"] = [{"path": "/ok", "host": "127.0.0.1", "port": 80, "scheme": "http"}]
    plan = health.plans([item])[item["id"]]
    assert len(plan["targets"]) == len(plan["errors"]) == 1
    assert health.aggregate([{"status": "up"}, *plan["errors"]]) == "partial"
