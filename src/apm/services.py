import secrets
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, update

from apm.db import Audit, Job, Resource, Revision, User, now, state_set, uid
from apm.schemas import ADMIN_KINDS, SCHEMAS, ResourceInput
from apm.security import Vault, atomic_write, digest


def audit(session, actor, action, object_id=None, **detail):
    session.add(
        Audit(
            actor=actor.email if isinstance(actor, User) else actor,
            action=action,
            object_id=object_id,
            detail=detail,
        )
    )


def serialize(resource, role="admin"):
    import copy

    data = copy.deepcopy(resource.data)
    if role != "admin":
        for key in ("advanced", "http_snippet", "stream_snippet"):
            data.pop(key, None)
    return {
        "id": resource.id,
        "kind": resource.kind,
        "name": resource.name,
        "data": data,
        "version": resource.version,
        "enabled": resource.enabled,
        "source": resource.source,
        "has_credentials": bool(resource.secret),
    }


def snapshot(session):
    # Revision snapshots are private worker inputs, never API responses.
    return [
        {**serialize(r), "encrypted_secret": r.secret}
        for r in session.scalars(select(Resource).order_by(Resource.kind, Resource.id))
    ]


def enqueue(session, kind: str, payload: dict, context=None) -> Job:
    import time

    if context is None and payload.get("resource_id"):
        resource = session.get(Resource, payload["resource_id"])
        if resource:
            context = {"name": resource.name, "kind": resource.kind}
    payload = {**payload, **({"_context": context} if context else {})}
    job = Job(id=uid(), kind=kind, payload=payload, sequence=time.time_ns())
    session.add(job)
    session.flush()
    return job


def enqueue_apply(session, context=None):
    session.flush()
    revision = Revision(id=uid(), snapshot=snapshot(session))
    session.add(revision)
    session.flush()
    owner = session.info.get("apply_owner", {})
    job = enqueue(session, "apply", {
        "revision_id": revision.id,
        "confirmation": "manual" if owner else "automatic",
        **owner,
    }, context=context)
    return {"operation_id": job.id, "revision_id": revision.id}


def sync_safety(session, result):
    """Reconcile the agent's durable outcome, including after a worker/manager restart."""
    from apm.db import state_get

    revision_id = result.get("revision_id")
    revision = session.get(Revision, revision_id) if revision_id else None
    status = result.get("status", "applied")
    if result.get("halted") or (revision and revision.status != status
                                and status in ("rolled_back", "rollback_failed")):
        state_set(session, "apply_halted", {"halted": True, "revision_id": revision_id})
    if not revision or status not in ("applied", "awaiting_confirmation", "rolled_back", "rollback_failed"):
        return
    if revision.status == status:
        return
    revision.status = status
    revision.generation = result.get("generation")
    error = None
    if status in ("rolled_back", "rollback_failed"):
        error = ("rollback_failed: local recovery required" if status == "rollback_failed"
                 else "previous revision restored: " + result.get("reason", "rollback"))
        revision.error = error
        if result.get("previous_revision_id"):
            applied = state_get(session, "applied", {})
            state_set(session, "applied", {
                **applied, "revision_id": result["previous_revision_id"],
                "generation": result.get("rollback_generation"),
            })
    if status == "applied" and result.get("active_revision", revision_id) == revision_id:
        state_set(session, "applied", result)
    for job in session.scalars(select(Job).where(Job.kind == "apply")):
        if job.payload.get("revision_id") != revision_id:
            continue
        job.status = ("succeeded" if status == "applied" else "awaiting_confirmation"
                      if status == "awaiting_confirmation" else "failed")
        job.result = {**job.result, **result}
        job.error = error
        job.updated_at = now()
    audit(session, "agent", "revision." + status, revision_id, generation=result.get("generation"))


def require_role(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Insufficient permissions")


def get_resource(session, kind, object_id):
    obj = session.get(Resource, object_id)
    if not obj or obj.kind != kind:
        raise HTTPException(404, "Resource not found")
    return obj


def check_references(session, data):
    reference_kinds = {
        "certificate_id": "certificates",
        "dns_profile_id": "dns-profiles",
        "upstream_id": "upstreams",
        "auth_provider_id": "auth-providers",
        "header_policy_id": "header-policies",
        "tls_policy_id": "tls-policies",
        "client_ca_id": "client-cas",
        "geo_policy_id": "geo-policies",
        "crowdsec_profile_id": "crowdsec-profiles",
        "ech_id": "ech",
    }
    for key, kind in reference_kinds.items():
        if value := data.get(key):
            obj = get_resource(session, kind, value)
            if not obj.enabled:
                raise HTTPException(422, f"Referenced {kind} is disabled")
    for value in data.get("access_ids", []):
        get_resource(session, "access-lists", value)
    for location in data.get("locations", []):
        check_references(session, location)


def conflicts(session, kind, data, object_id=None):
    if kind == "runtime":
        other = session.scalar(select(Resource).where(Resource.kind == "runtime", Resource.id != object_id))
        if other:
            raise HTTPException(409, "Only one runtime configuration is allowed")
    existing = session.scalars(select(Resource).where(Resource.enabled.is_(True), Resource.id != object_id))
    for other in existing:
        if kind in ("proxy-hosts", "redirect-hosts", "sites") and other.kind in (
            "proxy-hosts",
            "redirect-hosts",
            "sites",
        ):
            if set(data.get("domains", [])) & set(other.data.get("domains", [])):
                raise HTTPException(409, "Domain already managed by another resource")
        if kind == other.kind == "streams":
            if (data["listen_port"], data["protocol"]) == (other.data["listen_port"], other.data["protocol"]):
                raise HTTPException(409, "Port already managed")


def save_resource(session, config, user, kind: str, payload: ResourceInput, object_id=None, expected=None):
    if kind not in SCHEMAS:
        raise HTTPException(404, "Unknown resource kind")
    require_role(user, "admin", "operator")
    if kind in ADMIN_KINDS or (payload.credentials is not None and kind != "access-lists"):
        require_role(user, "admin")
    old = get_resource(session, kind, object_id) if object_id else None
    if user.role != "admin" and old and "advanced" not in payload.data and "advanced" in old.data:
        payload.data = {**payload.data, "advanced": old.data["advanced"]}
    try:
        data = SCHEMAS[kind].model_validate(payload.data).model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if old and old.source == "docker":
        raise HTTPException(409, "Edit the source Docker labels instead")
    if user.role != "admin":
        previous = old.data if old else {}

        def protected(value):
            fields = (
                "advanced",
                "crowdsec_profile_id",
                "auth_provider_id",
                "tls_policy_id",
                "header_policy_id",
                "client_ca_id",
                "geo_policy_id",
            )
            return {k: value.get(k) or None for k in fields}

        if protected(data) != protected(previous):
            raise HTTPException(403, "Administrative policy change")
        previous_locations = {loc.get("path"): loc for loc in previous.get("locations", [])}
        current_locations = {loc.get("path"): loc for loc in data.get("locations", [])}
        for path in set(previous_locations) | set(current_locations):
            if protected(current_locations.get(path, {})) != protected(previous_locations.get(path, {})):
                raise HTTPException(403, "Administrative policy change")
        if old and old.data.get("advanced", "") != data.get("advanced", ""):
            raise HTTPException(403, "Only administrators may change snippets")
    check_references(session, data)
    if (
        user.role != "admin"
        and data.get("dns_profile_id")
        and (
            not old
            or old.data.get("dns_profile_id") != data["dns_profile_id"]
            or old.data.get("tls") != data.get("tls")
        )
    ):
        profile = get_resource(session, "dns-profiles", data["dns_profile_id"])
        if not profile.data.get("operator_allowed"):
            raise HTTPException(403, "DNS profile is not authorized for operators")
    if data.get("certificate_id") and data.get("domains"):
        from apm.certificates import covered

        cert = get_resource(session, "certificates", data["certificate_id"])
        if cert.data.get("status") == "ready" and not all(
            covered(name, cert.data.get("domains", [])) for name in data["domains"]
        ):
            raise HTTPException(422, "Selected certificate does not cover the route domains")
    if payload.enabled:
        conflicts(session, kind, data, object_id)
    if kind == "access-lists" and payload.credentials is not None:
        from passlib.hash import sha512_crypt

        data["users"] = sorted(payload.credentials)
        try:
            SCHEMAS[kind].model_validate(data)
        except ValueError:
            raise HTTPException(422, "Invalid Basic Auth username") from None
        if any(not password or len(password) > 1024 for password in payload.credentials.values()):
            raise HTTPException(422, "Basic Auth passwords must have 1 to 1024 characters")
        payload.credentials = {
            name: sha512_crypt.hash(password, rounds=100000) for name, password in payload.credentials.items()
        }
    if kind == "certificates":
        for field in ("status", "fingerprint", "expires_at"):
            data[field] = old.data.get(field) if old else CertificateDefaults[field]
    if kind == "client-cas":
        data["fingerprint"] = old.data.get("fingerprint") if old else None
    if kind == "geo-policies":
        from apm.db import state_get

        data["database_version"] = (
            old.data.get("database_version", "")
            if old
            else state_get(session, "geoip_database", {}).get("version", "")
        )
    if kind == "ech":
        for field in ("status", "config", "current_key", "previous_key", "pending_key"):
            data[field] = old.data.get(field, "") if old else ("pending" if field == "status" else "")
    encrypted = (
        Vault(config.data_dir).encrypt(payload.credentials) if payload.credentials is not None else None
    )
    if old:
        if expected is None:
            raise HTTPException(428, "If-Match resource version required")
        if old.version != expected:
            raise HTTPException(409, "Resource changed; reload before saving")
        values = {
            "data": data,
            "name": payload.name,
            "enabled": payload.enabled,
            "version": old.version + 1,
            "updated_at": now(),
        }
        if encrypted is not None:
            values["secret"] = encrypted
        result = session.execute(
            update(Resource).where(Resource.id == old.id, Resource.version == expected).values(**values)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "Concurrent update")
        session.expire(old)
        obj = old
    else:
        obj = Resource(
            id=uid(), kind=kind, name=payload.name, data=data, secret=encrypted, enabled=payload.enabled
        )
        session.add(obj)
    session.flush()
    audit(session, user, "resource.update" if old else "resource.create", obj.id, kind=kind)
    context = {"name": obj.name, "kind": kind}
    from apm.certificates import enqueue_issuance

    if kind == "proxy-hosts" and data["tls"] in ("http", "dns") and not data.get("certificate_id"):
        certificate = Resource(
            id=uid(),
            kind="certificates",
            name=payload.name,
            data={
                "domains": data["domains"],
                "mode": data["tls"],
                "dns_profile_id": data["dns_profile_id"],
                "email": data["acme_email"],
                "terms_agreed": data["acme_terms_agreed"],
                "server": config.acme_server,
                "status": "pending",
                "key_type": "ecdsa",
            },
        )
        session.add(certificate)
        obj.data = {**data, "certificate_id": certificate.id}
        session.flush()
        operation = enqueue_apply(session, context=context)
        enqueue_issuance(session, certificate.id)
    else:
        operation = enqueue_apply(session, context=context)
    if kind == "certificates" and data["mode"] != "custom":
        enqueue_issuance(session, obj.id)
    return {**serialize(obj, user.role), **operation}


CertificateDefaults = {"status": "pending", "fingerprint": None, "expires_at": None}


def bootstrap_token(session, root: Path):
    if session.scalar(select(User.id).limit(1)):
        raise ValueError("Setup already completed")
    token_path = root / "setup.token"
    if token_path.exists():
        return token_path.read_text().strip()
    token = secrets.token_urlsafe(32)
    atomic_write(token_path, token.encode())
    state_set(session, "setup", {"digest": digest(token)})
    return token
