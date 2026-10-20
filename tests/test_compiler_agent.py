import uuid

import pytest
from pydantic import ValidationError

from apm.agent import Agent, Deployment
from apm.compiler import CompileError, Compiler, q
from apm.schemas import Access, Route, Stream


def resource(kind, data, object_id=None):
    return {"id": object_id or str(uuid.uuid4()), "kind": kind, "data": data, "enabled": True}


def test_tls_pending_never_exposes_plaintext_backend(config):
    data = Route(domains=["example.com"], tls="http", acme_terms_agreed=True).model_dump()
    text = (
        Compiler(config, {}, config.data_dir / "revisions/test")
        .compile([resource("proxy-hosts", data)])
        .config
    )
    assert "location / { return 503; }" in text
    assert 'proxy_pass "http://127.0.0.1:8080' not in text
    assert "/.well-known/acme-challenge/" in text


def test_acl_preserves_order_and_hashes(config):
    acl_id = str(uuid.uuid4())
    access = Access(rules=[{"action": "allow", "address": "10.0.0.0/8"}], users=["user"]).model_dump()
    route = Route(
        domains=["пример.рф"], access_ids=[acl_id], locations=[{"path": "/api", "access_ids": [acl_id]}]
    ).model_dump()
    result = Compiler(
        config, {}, config.data_dir / "revisions/test", lambda _: {"user": "$6$abc$hash"}
    ).compile([resource("access-lists", access, acl_id), resource("proxy-hosts", route)])
    assert "allow 10.0.0.0/8;\ndeny all;" in result.config
    assert "xn--e1afmkfd.xn--p1ai" in result.config
    assert any("user:$6$abc$hash" in value for value in result.files.values())


def test_missing_module_is_explicit(config):
    route = Route(domains=["example.com"], compression="brotli").model_dump()
    with pytest.raises(CompileError, match="brotli"):
        Compiler(config, {}, config.data_dir).compile([resource("proxy-hosts", route)])


def test_directive_values_and_ports():
    assert q('a"; return 200; $x') == '"a\\"; return 200; \\$x"'
    with pytest.raises(CompileError):
        q("unsafe\nvalue")
    with pytest.raises(ValidationError):
        Stream(listen_port=81, host="127.0.0.1", port=8080)
    with pytest.raises(ValidationError):
        Route(domains=["valid.example"], host="host; } events {}")


def test_immutable_bundle_and_no_path_traversal(config):
    agent = Agent(config)
    revision = str(uuid.uuid4())
    deployment = Deployment(revision_id=revision, configuration="events {}", files={"auth/user": "hash"})
    assert agent.stage(deployment) == agent.stage(deployment)
    with pytest.raises(ValueError, match="immutable"):
        agent.stage(Deployment(revision_id=revision, configuration="changed"))
    with pytest.raises(ValueError, match="path"):
        agent.stage(Deployment(revision_id=uuid.uuid4(), configuration="", files={"../escape": "no"}))
    assert not (config.data_dir / "escape").exists()


def test_basic_auth_without_password_cannot_become_public(config):
    acl_id = str(uuid.uuid4())
    access = Access(users=["missing-password"]).model_dump()
    route = Route(domains=["example.com"], access_ids=[acl_id]).model_dump()
    with pytest.raises(CompileError, match="without a password"):
        Compiler(config, {}, config.data_dir).compile(
            [resource("access-lists", access, acl_id), resource("proxy-hosts", route)]
        )


def test_public_location_is_an_explicit_exception(config):
    acl_id = str(uuid.uuid4())
    access = Access(rules=[{"action": "deny", "address": "all"}]).model_dump()
    route = Route(
        domains=["example.com"], access_ids=[acl_id], locations=[{"path": "/public", "access_mode": "public"}]
    ).model_dump()
    text = (
        Compiler(config, {}, config.data_dir)
        .compile([resource("access-lists", access, acl_id), resource("proxy-hosts", route)])
        .config
    )
    public = text.split("location /public {", 1)[1].split("}", 1)[0]
    assert "deny all" not in public
    assert "deny all" in text


def test_failed_reload_restores_previous_generation(config, monkeypatch):
    agent = Agent(config)
    old = Deployment(revision_id=uuid.uuid4(), configuration="previous")
    agent.stage(old)
    agent.switch(str(old.revision_id))
    monkeypatch.setattr(agent, "command", lambda *args: "syntax valid")
    monkeypatch.setattr(agent, "generation", lambda: 1)
    attempts = []

    def reload(before):
        attempts.append(agent.current())
        if len(attempts) == 1:
            raise ValueError("simulated failed reload")
        return 2

    monkeypatch.setattr(agent, "reload", reload)
    candidate = Deployment(revision_id=uuid.uuid4(), configuration="candidate")
    with pytest.raises(ValueError, match="previous revision restored"):
        agent.apply(candidate)
    assert attempts == [str(candidate.revision_id), str(old.revision_id)]
    assert agent.current() == str(old.revision_id)
    assert not (config.data_dir / "run/apply-journal.json").exists()
