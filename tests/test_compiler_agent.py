import re
import uuid

import pytest
from pydantic import ValidationError

from apm.agent import Agent, Deployment
from apm.compiler import CompileError, Compiler, q
from apm.schemas import Access, AuthProvider, Route, Stream


def resource(kind, data, object_id=None, name=None):
    return {"id": object_id or str(uuid.uuid4()), "kind": kind, "data": data, "enabled": True,
            **({"name": name} if name is not None else {})}


def bundle_text(bundle):
    return "\n".join([bundle.config, *bundle.files.values()])


def test_auth_identity_variables_fit_default_linux_hash_buckets(config):
    provider_id = str(uuid.uuid4())
    provider = AuthProvider(provider="authentik", url="https://auth.example.test",
                            signin_url="https://auth.example.test/login", identity_headers=[
                                "Remote-User", "Remote-Email", "Remote-Groups",
                                "X-Auth-Request-User", "X-Auth-Request-Email",
                                "X-Authentik-Username", "X-Authentik-Email", "X-Authentik-Groups",
                            ]).model_dump()
    route = Route(domains=["app.example.test"], auth_provider_id=provider_id,
                  locations=[{"path": "/api"}]).model_dump()
    text = bundle_text(Compiler(config, {}, config.data_dir / "revisions/test").compile([
        resource("auth-providers", provider, provider_id), resource("proxy-hosts", route),
    ]))
    variables = re.findall(r"auth_request_set \$(\w+) ", text)
    assert len(variables) == 16 and len(set(variables)) == 16
    # ngx_hash_elt_t: pointer + aligned (length field + key + null), plus bucket terminator.
    assert all(8 + ((2 + len(name) + 1 + 7) // 8) * 8 + 8 <= 64 for name in variables)
    assert "proxy_ssl_server_name on;" in text
    assert 'proxy_ssl_name "auth.example.test";' in text


def test_tls_pending_never_exposes_plaintext_backend(config):
    data = Route(domains=["example.com"], tls="http", acme_terms_agreed=True).model_dump()
    text = bundle_text(
        Compiler(config, {}, config.data_dir / "revisions/test")
        .compile([resource("proxy-hosts", data)])
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
    assert "allow 10.0.0.0/8;\ndeny all;" in bundle_text(result)
    assert "xn--e1afmkfd.xn--p1ai" in bundle_text(result)
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
    text = bundle_text(
        Compiler(config, {}, config.data_dir)
        .compile([resource("access-lists", access, acl_id), resource("proxy-hosts", route)])
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


@pytest.mark.parametrize('mode', ['managed', 'existing'])
def test_resource_fragments_names_context_order_and_rename(config, mode):
    from apm.schemas import Redirect, Site, Upstream

    config.angie_mode = mode
    objects = [
        resource('proxy-hosts', Route(domains=['example.com'], upstream_id='pool').model_dump(), 'proxy', 'test'),
        resource('redirect-hosts', Redirect(domains=['redirect.example.com'], target='https://example.com').model_dump(), 'redirect', 'test'),
        resource('sites', Site(domains=['site.example.com'], root_id='test').model_dump(), 'site', 'test'),
        resource('streams', Stream(listen_port=19090, host='127.0.0.1', port=8080, upstream_id='pool').model_dump(), 'tcp', 'test'),
        resource('streams', Stream(listen_port=19091, host='127.0.0.1', port=8080, upstream_id='pool').model_dump(), 'tcp2', 'another'),
        resource('upstreams', Upstream(peers=[{'host': '127.0.0.1'}]).model_dump(), 'pool', 'pool'),
    ]
    first = Compiler(config, {}, config.data_dir / 'revisions/one').compile(objects)
    assert {'http/test.proxy.conf', 'http/test.redirect.conf', 'http/test.site.conf',
            'stream/test.stream.conf', 'http/pool.upstream.conf', 'stream/pool.upstream.conf'} <= first.files.keys()
    main = first.files['http.conf'] if mode == 'existing' else first.config
    assert main.index('pool.upstream.conf') < main.index('test.proxy.conf')
    streams = first.files['stream.conf'] if mode == 'existing' else first.config
    assert streams.count('stream/pool.upstream.conf') == 1
    assert 'server_name example.com;' in first.files['http/test.proxy.conf']
    objects[0]['name'] = 'renamed'
    second = Compiler(config, {}, config.data_dir / 'revisions/two').compile(objects)
    assert 'http/renamed.proxy.conf' in second.files
    assert 'http/test.proxy.conf' not in second.files
    assert 'http/test.proxy.conf' in first.files
    second = Compiler(config, {}, config.data_dir / 'revisions/three').compile(objects[1:])
    assert 'http/renamed.proxy.conf' not in second.files


def test_fragment_names_are_safe_and_deterministic_on_collisions(config):
    import re

    route = Route(domains=['example.com']).model_dump()
    objects = [resource('proxy-hosts', route, name='../../Тест / host', object_id='one'),
               resource('proxy-hosts', route, name='.. Тест / host', object_id='two'),
               resource('proxy-hosts', route, name='💡', object_id='three'),
               resource('proxy-hosts', route, name='pool\n"; } /host', object_id='four')]
    one = Compiler(config, {}, config.data_dir).compile(objects)
    two = Compiler(config, {}, config.data_dir).compile(list(reversed(objects)))
    assert one.files == two.files
    assert len(one.files) == 4
    for name in one.files:
        assert re.fullmatch(r'http/[a-z0-9_-]+\.proxy\.conf', name)
    assert len([name for name in one.files if name.startswith('http/test-host-')]) == 2
