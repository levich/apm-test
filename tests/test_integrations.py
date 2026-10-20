import base64
import json
import struct
from urllib.parse import parse_qs

import httpx
import pyotp
import pytest
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select

from apm.db import Database, Resource, state_set
from apm.discovery import desired_routes, reconcile
from apm.dns import Cloudru, Regru, Selectel, Webnames, Yandex
from apm.ech import key_pair
from apm.gateway import allowed
from apm.schemas import DNSProfile
from apm.services import enqueue
from apm.worker import Worker


@pytest.mark.parametrize("provider", [Yandex, Regru, Selectel, Webnames, Cloudru])
def test_provider_preserves_foreign_values(config, provider):
    values = ["existing-owner"]
    operations = []
    name = "_acme-challenge.example.com"

    def handler(request):
        operations.append(request.method)
        body = (
            json.loads(request.content)
            if request.content and request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        form = (
            {key: val[0] for key, val in parse_qs(request.content.decode()).items()}
            if request.content and not body
            else {}
        )
        if provider is Yandex:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "name": name + ".",
                        "type": "TXT",
                        "ttl": "300",
                        "data": [json.dumps(v) for v in values],
                    },
                )
            values[:] = [json.loads(v) for v in body["additions"][0]["data"]] if body["additions"] else []
            return httpx.Response(200, json={"done": True})
        if provider is Regru:
            payload = json.loads(form["input_data"])
            if request.url.path.endswith("get_resource_records"):
                return httpx.Response(
                    200,
                    json={
                        "result": "success",
                        "answer": {
                            "domains": [
                                {
                                    "rrs": [
                                        {"rectype": "TXT", "subname": "_acme-challenge", "content": v}
                                        for v in values
                                    ]
                                }
                            ]
                        },
                    },
                )
            if request.url.path.endswith("add_txt"):
                values.append(payload["text"])
            if request.url.path.endswith("remove_record"):
                values.remove(payload["content"])
            return httpx.Response(200, json={"result": "success"})
        if provider is Webnames:
            command = form["thisPage"]
            if command == "pispDomainZoneInfo":
                return httpx.Response(
                    200, text="\n".join(f"subname:_acme-challenge;rectype:TXT;address:{v};" for v in values)
                )
            if command == "pispDomainZoneAddTXT":
                values.append(form["text"])
            if command == "pispDomainZoneRmRR":
                values.remove(form["address"])
            return httpx.Response(200, text="Success")
        if request.method == "GET":
            record = {
                "id": "record",
                "name": name + ".",
                "type": "TXT",
                "ttl": 300,
                "records": [{"content": json.dumps(v)} for v in values],
                "values": [json.dumps(v) for v in values],
            }
            return httpx.Response(200, json={"result": [record], "records": [record]})
        values[:] = (
            [json.loads(v["content"]) for v in body["records"]]
            if provider is Selectel
            else [json.loads(v) for v in body["values"]]
        )
        return httpx.Response(200, json={})

    profile = DNSProfile(provider=provider.provider, zone="example.com", zone_id="zone-id").model_dump()
    adapter = provider(
        config,
        profile,
        {"iam_token": "fake", "token": "fake", "username": "fake", "password": "fake"},
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    handle = adapter.present(name, "our-challenge")
    assert values == ["existing-owner", "our-challenge"]
    values.append("parallel-owner")
    adapter.cleanup(handle)
    assert values == ["existing-owner", "parallel-owner"]


def test_gateway_denies_sensitive_and_mutating_apis():
    assert allowed("GET", "/v1.47/containers/json")
    assert allowed("GET", "/events")
    for method, path in [
        ("POST", "/containers/create"),
        ("GET", "/containers/id/json"),
        ("GET", "/secrets"),
        ("GET", "/containers/id/archive"),
        ("DELETE", "/containers/id"),
    ]:
        assert not allowed(method, path)


def test_ech_config_matches_private_key():
    pem, encoded = key_pair("public.example.com", config_id=10)
    private = serialization.load_pem_private_key(pem, None)
    raw = base64.b64decode(encoded)
    length, version, content_length = struct.unpack("!HHH", raw[:6])
    assert length == len(raw) - 2 and version == 0xFE0D and content_length == len(raw) - 6
    assert raw[6] == 10
    assert raw[11:43] == private.public_key().public_bytes_raw()
    assert b"public.example.com" in raw


def test_totp_cannot_bypass_pending_session_and_recovery_is_single_use(admin):
    enrollment = admin.post("/api/v1/auth/mfa/enroll", json={"password": "test-password-12345"}).json()
    confirmation = admin.post(
        "/api/v1/auth/mfa/confirm", json={"code": pyotp.TOTP(enrollment["secret"]).now()}
    )
    assert confirmation.status_code == 200
    recovery = confirmation.json()["recovery_codes"][0]
    login = admin.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "test-password-12345"}
    )
    assert login.json()["mfa_required"]
    assert admin.get("/api/v1/users").status_code == 401
    assert admin.post("/api/v1/auth/mfa/verify", json={"code": recovery}).status_code == 200
    admin.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "test-password-12345"})
    assert admin.post("/api/v1/auth/mfa/verify", json={"code": recovery}).status_code == 401


def container(domain="app.example.com"):
    return {
        "Labels": {"apm.enable": "true", "apm.host": domain, "apm.network": "apps", "apm.port": "8080"},
        "State": "running",
        "NetworkSettings": {"Networks": {"apps": {"IPAddress": "172.20.0.2"}}},
    }


def test_discovery_reconciliation_recovers_missed_events(config):
    config.discovery_enabled, config.discovery_domains, config.discovery_networks = (
        True,
        ["example.com"],
        ["apps"],
    )
    db = Database(config)
    db.initialize()
    containers = [container()]
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=containers)),
        base_url="http://docker",
    )
    assert reconcile(db, config, client)["changed"] == 2
    assert reconcile(db, config, client)["changed"] == 0
    containers.clear()
    assert reconcile(db, config, client)["changed"] == 1
    with db.session() as session:
        assert not session.scalar(select(Resource).where(Resource.kind == "proxy-hosts")).enabled
    with pytest.raises(ValueError, match="allowlist"):
        desired_routes([container("other.domain.test")], config)


def test_jobs_are_fifo_and_cleanup_runs_when_apply_is_halted(config):
    db = Database(config)
    db.initialize()
    worker = Worker(config, db)
    with db.session() as session:
        first = enqueue(session, "apply", {})
        second = enqueue(session, "dns.cleanup", {})
    assert worker.claim() == first.id
    with db.session() as session:
        state_set(session, "apply_halted", {"halted": True})
    assert worker.claim() == second.id
