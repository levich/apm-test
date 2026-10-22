import pytest
from sqlalchemy import select

from apm.db import Job, Resource


@pytest.mark.parametrize("mode", ["http", "dns"])
def test_inline_certificate_is_linked_and_queued_after_apply(admin, config, mode):
    data = {
        "domains": ["example.com"],
        "host": "127.0.0.1",
        "port": 8080,
        "tls": mode,
        "acme_email": "certificates@example.com",
        "acme_terms_agreed": True,
    }
    if mode == "dns":
        profile = admin.post(
            "/api/v1/resources/dns-profiles",
            json={
                "name": "DNS",
                "data": {"provider": "regru", "zone": "example.com"},
            },
        )
        assert profile.status_code == 201, profile.text
        data["dns_profile_id"] = profile.json()["id"]
        data["domains"] = ["*.example.com", "example.com"]
    response = admin.post("/api/v1/resources/proxy-hosts", json={"name": "New SSL host", "data": data})
    assert response.status_code == 201, response.text
    host = response.json()
    certificate_id = host["data"]["certificate_id"]
    with admin.app.state.db.session() as session:
        certificate = session.get(Resource, certificate_id)
        assert certificate.kind == "certificates"
        assert certificate.data["mode"] == mode
        assert certificate.data["email"] == data["acme_email"]
        assert certificate.data["domains"] == data["domains"]
        assert certificate.data["terms_agreed"] is True
        assert certificate.data["server"] == config.acme_server
        assert certificate.data["status"] == "pending"
        issue = session.scalar(select(Job).where(Job.kind == "certificate.issue"))
        assert issue.payload["resource_id"] == certificate_id
        assert issue.payload["_context"] == {"name": "New SSL host", "kind": "certificates"}
        assert session.get(Job, host["operation_id"]).sequence < issue.sequence

    # Reopening and saving a pending managed certificate keeps the same request.
    updated = admin.put(
        "/api/v1/resources/proxy-hosts/" + host["id"],
        headers={"If-Match": str(host["version"])},
        json={"name": "Edited SSL host", "data": {**host["data"], "websocket": False}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["certificate_id"] == certificate_id
    assert len(admin.get("/api/v1/resources/certificates").json()) == 1
    with admin.app.state.db.session() as session:
        assert len(list(session.scalars(select(Job).where(Job.kind == "certificate.issue")))) == 1


@pytest.mark.parametrize(
    "tls,domains,terms",
    [
        ("http", ["example.com"], False),
        ("http", ["*.example.com"], True),
        ("dns", ["example.com"], True),
    ],
)
def test_invalid_inline_certificate_does_not_leave_resources(admin, tls, domains, terms):
    response = admin.post(
        "/api/v1/resources/proxy-hosts",
        json={
            "name": "Invalid SSL host",
            "data": {
                "domains": domains,
                "tls": tls,
                "acme_terms_agreed": terms,
            },
        },
    )
    assert response.status_code == 422
    assert admin.get("/api/v1/resources/proxy-hosts").json() == []
    assert admin.get("/api/v1/resources/certificates").json() == []


def test_editing_can_explicitly_request_a_replacement_certificate(admin):
    data = {"domains": ["example.com"], "tls": "http", "acme_terms_agreed": True}
    host = admin.post("/api/v1/resources/proxy-hosts", json={"name": "Host", "data": data}).json()
    old_id = host["data"]["certificate_id"]
    result = admin.put(
        "/api/v1/resources/proxy-hosts/" + host["id"],
        headers={"If-Match": str(host["version"])},
        json={"name": "Host", "data": {**host["data"], "certificate_id": None}},
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["certificate_id"] != old_id
    assert len(admin.get("/api/v1/resources/certificates").json()) == 2
