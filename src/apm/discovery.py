import json
import threading
from collections import defaultdict

import httpx
from sqlalchemy import select

from apm.db import Job, Resource, now, uid
from apm.schemas import Route, Upstream, hostname
from apm.services import audit, conflicts, enqueue, enqueue_apply


def desired_routes(containers, config):
    if not config.discovery_networks or not config.discovery_domains:
        raise ValueError("Discovery requires explicit network and domain allowlists")
    groups = defaultdict(list)
    for container in containers:
        labels = container.get("Labels") or {}
        if labels.get("apm.enable", "").lower() != "true":
            continue
        domain = hostname(labels.get("apm.host", ""))
        if not any(domain == zone or domain.endswith("." + zone) for zone in config.discovery_domains):
            raise ValueError("Docker domain is outside the discovery allowlist")
        network = labels.get("apm.network", "")
        if network not in config.discovery_networks:
            raise ValueError("Docker network is outside the discovery allowlist")
        tls = labels.get("apm.tls", "off")
        if tls not in ("off", "http", "dns"):
            raise ValueError("Invalid apm.tls label")
        port = int(labels.get("apm.port", "0"))
        ip = container.get("NetworkSettings", {}).get("Networks", {}).get(network, {}).get("IPAddress", "")
        active = container.get("State") == "running" and bool(ip)
        groups[domain].append(
            {
                "host": ip,
                "port": port,
                "active": active,
                "tls": tls,
                "scheme": labels.get("apm.scheme", "http"),
                "dns_profile": labels.get("apm.dns-profile"),
                "weight": int(labels.get("apm.weight", "1")),
            }
        )
    return groups


def reconcile(database, config, client=None):
    if not config.discovery_enabled:
        raise ValueError("Docker discovery is disabled")
    client = client or httpx.Client(base_url=config.docker_url, timeout=20, trust_env=False)
    response = client.get("/containers/json", params={"all": 1})
    response.raise_for_status()
    groups = desired_routes(response.json(), config)
    changed, seen, certificates = 0, set(), []
    with database.session() as s:
        for domain, members in groups.items():
            key = "docker:host:" + domain
            seen.add(key)
            peers = [p for p in members if p["active"]]
            existing = s.scalar(select(Resource).where(Resource.source_key == key))
            if not peers:
                if existing and existing.enabled:
                    existing.enabled = False
                    existing.version += 1
                    changed += 1
                continue
            first = peers[0]
            if any(
                (p["tls"], p["scheme"], p["dns_profile"])
                != (first["tls"], first["scheme"], first["dns_profile"])
                for p in peers
            ):
                raise ValueError("Conflicting Docker labels for the same host")
            dns_profile_id = None
            if first["tls"] != "off" and not config.discovery_acme_terms_agreed:
                raise ValueError("Administrator must accept ACME terms for discovery")
            if first["tls"] == "dns":
                profile = s.scalar(
                    select(Resource).where(
                        Resource.kind == "dns-profiles", Resource.name == first["dns_profile"]
                    )
                )
                if not profile or not profile.enabled or not profile.data.get("discovery_allowed"):
                    raise ValueError("DNS profile is not authorized for discovery")
                if domain != profile.data["zone"] and not domain.endswith("." + profile.data["zone"]):
                    raise ValueError("Docker domain is outside DNS profile zone")
                dns_profile_id = profile.id
            upstream_key = "docker:upstream:" + domain
            upstream = s.scalar(select(Resource).where(Resource.source_key == upstream_key))
            upstream_data = Upstream(
                peers=[{"host": p["host"], "port": p["port"], "weight": p["weight"]} for p in peers]
            ).model_dump()
            if not upstream:
                upstream = Resource(
                    id=uid(),
                    kind="upstreams",
                    name=domain,
                    source="docker",
                    source_key=upstream_key,
                    data=upstream_data,
                )
                s.add(upstream)
                changed += 1
            elif upstream.data != upstream_data:
                upstream.data, upstream.version = upstream_data, upstream.version + 1
                changed += 1
            route_data = Route(
                domains=[domain],
                host=first["host"],
                port=first["port"],
                scheme=first["scheme"],
                upstream_id=upstream.id,
                tls=first["tls"],
                dns_profile_id=dns_profile_id,
                certificate_id=existing.data.get("certificate_id") if existing else None,
                acme_email=config.acme_email,
                acme_terms_agreed=config.discovery_acme_terms_agreed,
            ).model_dump(mode="json")
            if not existing:
                conflicts(s, "proxy-hosts", route_data)
                existing = Resource(
                    id=uid(),
                    kind="proxy-hosts",
                    name=domain,
                    source="docker",
                    source_key=key,
                    data=route_data,
                )
                s.add(existing)
                changed += 1
            elif existing.data != route_data or not existing.enabled:
                existing.data, existing.enabled, existing.version = route_data, True, existing.version + 1
                changed += 1
            if route_data["tls"] != "off" and not route_data.get("certificate_id"):
                cert = Resource(
                    id=uid(),
                    kind="certificates",
                    name=domain,
                    source="docker",
                    data={
                        "domains": [domain],
                        "mode": first["tls"],
                        "dns_profile_id": dns_profile_id,
                        "email": config.acme_email,
                        "terms_agreed": True,
                        "status": "pending",
                        "server": config.acme_server,
                    },
                )
                s.add(cert)
                existing.data = {**route_data, "certificate_id": cert.id}
                certificates.append(cert.id)
        for existing in s.scalars(
            select(Resource).where(Resource.kind == "proxy-hosts", Resource.source == "docker")
        ):
            if existing.source_key not in seen and existing.enabled:
                existing.enabled, existing.version = False, existing.version + 1
                changed += 1
        if changed:
            audit(s, "discovery", "discovery.reconciled", changes=changed)
            enqueue_apply(s)
            for certificate_id in certificates:
                enqueue(s, "certificate.issue", {"resource_id": certificate_id})
    return {"changed": changed, "hosts": len(groups)}


def event_watcher(database, config, stop: threading.Event):
    """Reconnectable event trigger; periodic reconciliation covers missed events."""
    while not stop.is_set():
        try:
            with httpx.stream(
                "GET",
                config.docker_url + "/events",
                params={"filters": json.dumps({"type": ["container"]})},
                timeout=65,
                trust_env=False,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if stop.is_set():
                        return
                    if not line:
                        continue
                    with database.session() as s:
                        active = s.scalar(
                            select(Job.id).where(
                                Job.kind == "discovery.reconcile", Job.status.in_(["pending", "running"])
                            )
                        )
                        if not active:
                            job = enqueue(s, "discovery.reconcile", {})
                            job.available_at = now() + 2
        except (httpx.HTTPError, ValueError):
            stop.wait(3)
