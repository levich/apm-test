"""Backend checks performed by the Unix agent in Angie's network namespace."""

import hashlib
import http.client
import json
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from apm.db import Resource, State, now, state_get, state_set
from apm.schemas import hostname

INTERVAL = 30
TIMEOUT = 3
STALE_AFTER = 90


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str = Field(max_length=36)
    path: str = Field(default="/", max_length=2048, pattern=r"^/[^\r\n\x00 ]*$")
    route_path: str = "/"
    host: str
    port: int = Field(ge=1, le=65535)
    scheme: Literal["http", "https", "grpc", "grpcs"]
    host_header: str
    sni: str
    verify: bool = True
    backup: bool = False
    validate_hosts = field_validator("host", "host_header", "sni")(hostname)


class CheckRequest(BaseModel):
    targets: list[Target] = Field(max_length=32)


def plans(resources):
    objects = {r["id"]: r for r in resources}
    result = {}
    for obj in resources:
        if obj["kind"] != "proxy-hosts":
            continue
        data, targets, errors = obj["data"], [], []
        if obj["enabled"]:
            for location in [data, *data.get("locations", [])]:
                upstream_id = location.get("upstream_id")
                upstream = objects.get(upstream_id)
                peers = (
                    upstream["data"]["peers"]
                    if upstream and upstream["enabled"]
                    else []
                    if upstream_id
                    else [{"host": location["host"], "port": location["port"]}]
                )
                if not any(not peer.get("down") for peer in peers):
                    errors.append(
                        {
                            "resource_id": obj["id"],
                            "route_path": location["path"],
                            "host": location["host"],
                            "port": location["port"],
                            "status": "down",
                            "reason": "no_peers",
                            "backup": False,
                        }
                    )
                for peer in peers:
                    if peer.get("down"):
                        continue
                    try:
                        targets.append(
                            Target(
                                resource_id=obj["id"],
                                host=peer["host"],
                                port=peer["port"],
                                scheme=location["scheme"],
                                route_path=location["path"],
                                path="/" if location.get("strip_prefix") else location["path"],
                                host_header=data["domains"][0],
                                sni=data.get("upstream_sni") or location["host"],
                                verify=data.get("upstream_verify", True),
                                backup=peer.get("backup", False),
                            ).model_dump()
                        )
                    except ValidationError:
                        errors.append(
                            {
                                "resource_id": obj["id"],
                                "route_path": location["path"],
                                "host": peer["host"],
                                "port": peer["port"],
                                "status": "down",
                                "reason": "invalid_target",
                                "backup": peer.get("backup", False),
                            }
                        )
        signature = hashlib.sha256(json.dumps([targets, errors], sort_keys=True).encode()).hexdigest()
        result[obj["id"]] = {"signature": signature, "targets": targets, "errors": errors}
    return result


def probe(target):
    started = time.monotonic()
    connection = None
    sock = None
    result = {**target.model_dump(), "status": "down"}
    try:
        sock = socket.create_connection((target.host, target.port), TIMEOUT)
        if target.scheme in ("https", "grpcs"):
            context = ssl.create_default_context()
            if not target.verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            sock.settimeout(max(0.01, TIMEOUT - (time.monotonic() - started)))
            sock = context.wrap_socket(sock, server_hostname=target.sni)
        if target.scheme in ("http", "https"):
            sock.settimeout(max(0.01, TIMEOUT - (time.monotonic() - started)))
            connection = http.client.HTTPConnection(target.host, target.port, timeout=TIMEOUT)
            connection.sock = sock
            connection.putrequest("GET", target.path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", target.host_header)
            connection.putheader("User-Agent", "APM-Backend-Check/1")
            connection.putheader("Connection", "close")
            connection.endheaders()
            code = connection.getresponse().status
            result.update(
                http_status=code,
                status="up" if 200 <= code < 500 else "down",
                reason="http_response" if code < 500 else "http_error",
            )
        else:
            result.update(
                status="up", reason="tls_connected" if target.scheme == "grpcs" else "tcp_connected"
            )
    except ssl.SSLError:
        result["reason"] = "tls_error"
    except (TimeoutError, socket.timeout):
        result["reason"] = "timeout"
    except socket.gaierror:
        result["reason"] = "dns_error"
    except (OSError, http.client.HTTPException, ValueError):
        result["reason"] = "connection_error"
    finally:
        if connection:
            connection.close()
        if sock:
            sock.close()
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    result["checked_at"] = now()
    return result


def check(targets):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(probe, targets))


def aggregate(checks):
    if not checks or all(item["status"] == "down" for item in checks):
        return "down"
    if all(item["status"] == "up" for item in checks):
        return "up"
    return "partial"


def collect(database, client):
    from apm.services import serialize

    with database.session() as session:
        resources = [serialize(obj) for obj in session.scalars(select(Resource))]
    desired = plans(resources)
    targets = [target for plan in desired.values() for target in plan["targets"]]
    results = []
    for start in range(0, len(targets), 32):
        response = client.post("/backend-health", json={"targets": targets[start : start + 32]})
        response.raise_for_status()
        results.extend(response.json()["checks"])
    timestamp = now()
    with database.session() as session:
        for resource_id, plan in desired.items():
            checks = [item for item in results if item["resource_id"] == resource_id] + plan["errors"]
            state_set(
                session,
                "backend-health:" + resource_id,
                {
                    "signature": plan["signature"],
                    "checked_at": min(
                        (item.get("checked_at", timestamp) for item in checks), default=timestamp
                    ),
                    "status": aggregate(checks),
                    "checks": checks,
                },
            )
        for row in session.scalars(select(State).where(State.key.like("backend-health:%"))):
            if row.key.removeprefix("backend-health:") not in desired:
                session.delete(row)


def summary(session, resource, plan):
    if not resource.enabled:
        return {"status": "disabled", "checked_at": None, "checks": []}
    cached = state_get(session, "backend-health:" + resource.id, {})
    if cached.get("signature") != plan["signature"] or cached.get("checked_at", 0) < now() - STALE_AFTER:
        return {"status": "unknown", "checked_at": cached.get("checked_at"), "checks": []}
    return {key: cached[key] for key in ("status", "checked_at", "checks")}
