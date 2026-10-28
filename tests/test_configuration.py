import uuid

import pytest

from apm.agent import Agent, Deployment
from apm.compiler import Compiler
from apm.configuration import MAX_FILE_BYTES
from apm.nginx import Snippet, render_config
from apm.schemas import Route, Runtime, Stream


@pytest.fixture
def active(config):
    agent = Agent(config)
    deployment = Deployment(
        revision_id=uuid.uuid4(), configuration="events {}\n# current on disk\n",
        files={"http/portal.proxy.conf": 'server { return 200 "<script>text</script>"; }\n',
               "stream/mail.stream.conf": "server {}\n", "http.conf": "# HTTP includes\n",
               "stream.conf": "# TCP/UDP includes\n", "crowdsec.conf": "API_KEY=private\n",
               "auth/users.htpasswd": "private:hash\n", "default.html": "<h1>Page</h1>"},
    )
    agent.stage(deployment)
    agent.switch(str(deployment.revision_id))
    return agent, deployment


def test_configuration_requires_login(client):
    assert client.get("/api/v1/configuration").status_code == 401
    assert client.get("/api/v1/configuration/file", params={
        "revision_id": str(uuid.uuid4()), "path": "angie.conf"}).status_code == 401


@pytest.mark.parametrize("role", ["observer", "operator"])
def test_configuration_requires_admin(admin, role):
    assert admin.post("/api/v1/users", json={"email": role + "@example.com",
        "password": "test-password-12345", "role": role}).status_code == 201
    assert admin.post("/api/v1/auth/login", json={"email": role + "@example.com",
        "password": "test-password-12345"}).status_code == 200
    assert admin.get("/api/v1/configuration").status_code == 403
    assert admin.get("/api/v1/configuration/file", params={
        "revision_id": str(uuid.uuid4()), "path": "angie.conf"}).status_code == 403
    assert admin.get("/ui/configuration").status_code == 403
    assert 'href="/ui/configuration"' not in admin.get("/ui/dashboard").text


def test_no_active_configuration(admin, config):
    Agent(config).stage(Deployment(revision_id=uuid.uuid4(), configuration="staged only"))
    assert admin.get("/api/v1/configuration").json() == {
        "revision_id": None, "mode": "managed", "files": []}
    admin.cookies.set("apm_language", "ru")
    page = admin.get("/ui/configuration")
    assert page.status_code == 200
    assert "<h1>Конфигурация</h1>" in page.text
    admin.cookies.set("apm_language", "en")
    assert "<h1>Configuration</h1>" in admin.get("/ui/configuration").text


def test_current_files_are_exact_and_exclude_secrets(admin, active):
    _, deployment = active
    listing = admin.get("/api/v1/configuration")
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    result = listing.json()
    assert result["revision_id"] == str(deployment.revision_id)
    assert [item["path"] for item in result["files"]] == [
        "angie.conf", "http.conf", "http/portal.proxy.conf", "stream.conf", "stream/mail.stream.conf"]
    for item in result["files"]:
        response = admin.get("/api/v1/configuration/file", params={
            "revision_id": result["revision_id"], "path": item["path"]})
        assert response.status_code == 200
        contents = deployment.configuration if item["path"] == "angie.conf" else deployment.files[item["path"]]
        assert response.json()["content"] == contents
        assert item["size"] == len(contents.encode())


@pytest.mark.parametrize("name", ["../angie.conf", "/etc/passwd", "http/../../master.key",
    "auth/users.htpasswd", "crowdsec.conf", "default.html", "manifest.json", "http/missing.proxy.conf"])
def test_configuration_rejects_other_files(admin, active, name):
    _, deployment = active
    response = admin.get("/api/v1/configuration/file", params={
        "revision_id": str(deployment.revision_id), "path": name})
    assert response.status_code == 404


def test_configuration_tracks_apply_and_rollback(admin, active):
    agent, previous = active
    candidate = Deployment(revision_id=uuid.uuid4(), configuration="new configuration")
    agent.stage(candidate)
    assert admin.get("/api/v1/configuration").json()["revision_id"] == str(previous.revision_id)
    agent.switch(str(candidate.revision_id))
    assert admin.get("/api/v1/configuration").json()["revision_id"] == str(candidate.revision_id)
    params = {"revision_id": str(previous.revision_id), "path": "angie.conf"}
    assert admin.get("/api/v1/configuration/file", params=params).status_code == 409
    agent.switch(str(previous.revision_id))
    assert admin.get("/api/v1/configuration/file", params=params).json()["content"] == previous.configuration


def test_configuration_rejects_symlinks_and_large_files(admin, active, config):
    _, deployment = active
    directory = config.data_dir / "revisions" / str(deployment.revision_id)
    secret = config.data_dir / "secret.conf"
    secret.write_text("private")
    (directory / "http/leak.proxy.conf").symlink_to(secret)
    (directory / "angie.conf").unlink()
    (directory / "angie.conf").symlink_to(secret)
    paths = [item["path"] for item in admin.get("/api/v1/configuration").json()["files"]]
    assert "http/leak.proxy.conf" not in paths and "angie.conf" not in paths
    for name in ("angie.conf", "http/leak.proxy.conf"):
        assert admin.get("/api/v1/configuration/file", params={
            "revision_id": str(deployment.revision_id), "path": name}).status_code == 404
    (directory / "http.conf").write_text("x" * (MAX_FILE_BYTES + 1))
    assert admin.get("/api/v1/configuration/file", params={
        "revision_id": str(deployment.revision_id), "path": "http.conf"}).status_code == 413
    (config.data_dir / "current").unlink()
    (config.data_dir / "current").symlink_to(config.data_dir)
    assert admin.get("/api/v1/configuration").status_code == 409


def test_formatter_preserves_quoted_values_escapes_and_opaque_snippets():
    value = r'''add_header X-Example "a; {b} # c \\";'''
    snippet = '# own comment\nlocation ~ "/[a-z]{2}" { return 200 "${host};{}"; }'
    rendered = render_config(["server {", value, Snippet(snippet), "}"], "Example\nname")
    assert "# Example name\n" in rendered
    assert "\n    " + value + "\n" in rendered
    assert snippet in rendered
    assert rendered.endswith("\n}\n")


@pytest.mark.parametrize("mode", ["managed", "existing"])
def test_compiler_formats_generated_blocks_and_preserves_snippets(config, mode):
    config.angie_mode = mode
    snippet = '# keep original syntax\nlocation ~ "/[a-z]{2}" { return 200 "${host};{}"; }'
    resources = [
        {"id": "route", "kind": "proxy-hosts", "name": "Portal\nreturn 444;",
         "data": Route(domains=["portal.example.com"], advanced=snippet).model_dump()},
        {"id": "stream", "kind": "streams", "data": Stream(
            listen_port=19080, host="127.0.0.1", port=8080, advanced="  # tcp\n").model_dump()},
        {"id": "runtime", "kind": "runtime", "data": Runtime(http_snippet=snippet).model_dump()},
    ]
    bundle = Compiler(config, {}, config.data_dir / "revisions/test").compile(resources)
    proxy = bundle.files["http/portal-return-444.proxy.conf"]
    assert "# Proxy host: Portal return 444; (http)." in proxy
    assert "\nserver {\n    " in proxy
    assert "\n    location / {\n        " in proxy
    assert '\n        proxy_pass "http://127.0.0.1:8080";' in proxy
    assert "\n    location ^~ /.well-known/acme-challenge/ {\n        root " in proxy
    assert snippet in proxy
    main = bundle.files["http.conf"] if mode == "existing" else bundle.config
    assert snippet in main
    assert "map $http_upgrade $apm_connection {\n" in main
    assert "default upgrade;\n" in main
    if mode == "managed":
        assert "events {\n    worker_connections 1024;\n}" in main
        assert "\nhttp {\n    include " in main
