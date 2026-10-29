import json
import re
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apm import main
from apm.db import Resource, Revision
from apm.security import Vault


def host(domain="example.com"):
    return {"name": domain, "data": {"domains": [domain], "host": "127.0.0.1", "port": 8080}}


def test_updated_assets_get_new_urls_without_changing_app_version(admin, config, tmp_path, monkeypatch):
    def assets(client):
        pages = [client.get("/ui/configuration"), client.get("/login")]
        assert all(page.status_code == 200 for page in pages)
        urls = dict(re.findall(
            r'(?:src|href)="(/static/(?:app\.js|app\.css|login\.js))\?v=([a-f0-9]{16})"',
            "".join(page.text for page in pages),
        ))
        assert set(urls) == {"/static/app.js", "/static/app.css", "/static/login.js"}
        for path, version in urls.items():
            assert client.get(path, params={"v": version}).status_code == 200
        return urls

    previous = assets(admin)
    package = tmp_path / "package"
    shutil.copytree(main.PACKAGE / "templates", package / "templates")
    (package / "static").mkdir()
    for name in ("app.js", "app.css", "login.js"):
        shutil.copyfile(main.PACKAGE / "static" / name, package / "static" / name)
    with (package / "static/app.js").open("a") as source:
        source.write("\n// Next deployment\n")
    monkeypatch.setattr(main, "PACKAGE", package)
    with TestClient(main.create_app(config), base_url="https://testserver") as updated:
        updated.cookies.update(admin.cookies)
        current = assets(updated)
    assert current["/static/app.js"] != previous["/static/app.js"]
    assert current["/static/app.css"] == previous["/static/app.css"]
    assert current["/static/login.js"] == previous["/static/login.js"]


def test_setup_is_local_one_time_and_requires_strong_password(client, config):
    assert client.get("/api/v1/resources/proxy-hosts").status_code == 401
    body = {"email": "admin@example.com", "password": "test-password-12345", "token": "incorrect"}
    assert client.post("/api/v1/auth/setup", json=body).status_code == 403
    body["token"] = (config.data_dir / "setup.token").read_text().strip()
    assert client.post("/api/v1/auth/setup", json={**body, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/setup", json=body).status_code == 200
    assert not (config.data_dir / "setup.token").exists()
    assert client.post("/api/v1/auth/setup", json=body).status_code == 409


def test_csrf_and_origin(admin):
    assert (
        admin.post("/api/v1/resources/proxy-hosts", json=host(), headers={"X-CSRF-Token": "bad"}).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/v1/resources/proxy-hosts", json=host(), headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert admin.get("/api/docs").status_code == 200
    assert "frame-ancestors 'none'" in admin.get("/").headers["Content-Security-Policy"]


def test_versions_conflicts_and_domain_validation(admin):
    first = admin.post("/api/v1/resources/proxy-hosts", json=host()).json()
    path = "/api/v1/resources/proxy-hosts/" + first["id"]
    assert admin.put(path, json=host()).status_code == 428
    updated = admin.put(path, json=host(), headers={"If-Match": "1"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert admin.put(path, json=host(), headers={"If-Match": "1"}).status_code == 409
    assert admin.post("/api/v1/resources/proxy-hosts", json=host()).status_code == 409
    assert (
        admin.post("/api/v1/resources/proxy-hosts", json=host("bad; include /etc/passwd")).status_code == 422
    )


@pytest.mark.parametrize("role,expected", [("observer", 403), ("operator", 201)])
def test_direct_api_permissions(admin, role, expected):
    result = admin.post(
        "/api/v1/users",
        json={"email": role + "@example.com", "password": "test-password-12345", "role": role},
    )
    assert result.status_code == 201, result.text
    login = admin.post(
        "/api/v1/auth/login", json={"email": role + "@example.com", "password": "test-password-12345"}
    )
    admin.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert admin.post("/api/v1/resources/proxy-hosts", json=host()).status_code == expected
    assert (
        admin.post(
            "/api/v1/resources/dns-profiles",
            json={"name": "dns", "data": {"provider": "regru", "zone": "example.com"}},
        ).status_code
        == 403
    )
    assert admin.get("/api/v1/audit").status_code == 403
    assert (
        admin.post(
            "/api/v1/resources/proxy-hosts",
            json={"name": "unsafe", "data": {**host("other.example.com")["data"], "advanced": "return 200;"}},
        ).status_code
        == 403
    )


def test_operator_cannot_remove_administrator_protection(admin):
    policy = admin.post(
        "/api/v1/resources/header-policies", json={"name": "headers", "data": {"hsts": True}}
    ).json()
    body = host()
    body["data"]["header_policy_id"] = policy["id"]
    resource = admin.post("/api/v1/resources/proxy-hosts", json=body).json()
    admin.post(
        "/api/v1/users",
        json={"email": "operator@example.com", "password": "test-password-12345", "role": "operator"},
    )
    login = admin.post(
        "/api/v1/auth/login", json={"email": "operator@example.com", "password": "test-password-12345"}
    )
    admin.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    result = admin.put(
        "/api/v1/resources/proxy-hosts/" + resource["id"], json=host(), headers={"If-Match": "1"}
    )
    assert result.status_code == 403


def test_encrypted_secrets_are_private_but_available_to_revisions(admin, config):
    secret = "provider-password-do-not-expose"
    response = admin.post(
        "/api/v1/resources/dns-profiles",
        json={
            "name": "dns",
            "data": {"provider": "regru", "zone": "example.com"},
            "credentials": {"username": "test", "password": secret},
        },
    )
    assert response.status_code == 201, response.text
    assert secret not in response.text
    assert "encrypted_secret" not in admin.get("/api/v1/resources/dns-profiles").text
    with admin.app.state.db.session() as session:
        resource = session.scalar(select(Resource))
        assert secret not in resource.secret
        assert Vault(config.data_dir).decrypt(resource.secret)["password"] == secret
        revision = session.get(Revision, response.json()["revision_id"])
        assert revision.snapshot[0]["encrypted_secret"] == resource.secret
        assert secret not in json.dumps(revision.snapshot)


def test_htmx_and_local_assets(admin):
    assert admin.get("/ui/proxy-hosts").status_code == 200
    assert admin.get("/fragments/operations").status_code == 200
    assert admin.get("/static/vendor/tabler.min.css").status_code == 200


def test_parallel_writes_do_not_lose_edits(admin):
    from concurrent.futures import ThreadPoolExecutor

    created = admin.post("/api/v1/resources/proxy-hosts", json=host()).json()
    path = "/api/v1/resources/proxy-hosts/" + created["id"]

    def edit(name):
        return admin.put(path, json={**host(), "name": name}, headers={"If-Match": "1"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(edit, ["first", "second"]))
    assert sorted(statuses) == [200, 409]


def test_throttled_login(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "absent@example.com", "password": "invalid"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "absent@example.com", "password": "invalid"}
        ).status_code
        == 429
    )
