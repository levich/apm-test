import inspect
import re
from pathlib import Path

import pytest

from apm.cli import app
from apm.config import Settings
from apm.documentation import ROOT, guide, section_names
from apm.schemas import SCHEMAS, UserInput


def settings(schema, definitions, prefix=""):
    for key, spec in schema.get("properties", {}).items():
        path = prefix + key
        yield path, spec
        child = spec.get("items", spec)
        if "$ref" in child:
            child = definitions[child["$ref"].split("/")[-1]]
        if child.get("properties"):
            yield from settings(child, definitions, path + ".")


@pytest.mark.parametrize("language", ["ru", "en"])
def test_guide_covers_every_resource_field_environment_option_and_command(language):
    for kind, model in SCHEMAS.items():
        content = (ROOT / language / (kind + ".md")).read_text()
        schema = model.model_json_schema()
        assert "<!-- setting:name -->" in content
        assert "<!-- setting:enabled -->" in content
        for path, spec in settings(schema, schema.get("$defs", {})):
            assert f"<!-- setting:{path} -->" in content, (kind, path)
        assert "MISSING" not in content
    environment = (ROOT / language / "environment.md").read_text()
    for key in Settings.model_fields:
        assert "<!-- environment:APM_" + key.upper() + " -->" in environment
    users = (ROOT / language / "users.md").read_text()
    for key in UserInput.model_fields:
        assert f"<!-- setting:{key} -->" in users
    cli = (ROOT / language / "cli.md").read_text()
    for command in app.registered_commands:
        name = command.name or command.callback.__name__.replace("_", "-")
        assert f"<!-- command:{name} -->" in cli
        for key in inspect.signature(command.callback).parameters:
            assert f"<!-- option:{name}.{key} -->" in cli
    # Every label read by discovery must have documentation.
    discovery = Path("src/apm/discovery.py").read_text()
    labels = set(re.findall(r'labels\.get\("(apm\.[a-z-]+)"', discovery))
    for label in labels:
        assert f"<!-- label:{label} -->" in (ROOT / language / "discovery.md").read_text()
    assert set(path.stem for path in (ROOT / language).glob("*.md")) == set(section_names())


@pytest.mark.parametrize("language", ["ru", "en"])
def test_guide_credentials_links_and_rendering(language):
    for section in section_names():
        source = (ROOT / language / (section + ".md")).read_text()
        html, title = guide(section, language)
        assert title
        assert "&lt;!-- setting:" not in html
        for target in re.findall(r"\]\(([a-z-]+)\.md(?:#[\w.-]+)?\)", source):
            assert target in section_names(), (section, target)
            assert f"/ui/documentation/{target}" in html
    for section, keys in {
        "dns-profiles": [
            "username",
            "password",
            "iam_token",
            "service_account_id",
            "key_id",
            "private_key",
            "token",
            "domain_name",
            "project_id",
            "secret",
        ],
        "certificates": ["eab_kid", "eab_hmac_key"],
        "crowdsec-profiles": ["api_key", "site_key", "secret_key"],
        "geo-policies": ["account_id", "license_key"],
    }.items():
        source = (ROOT / language / (section + ".md")).read_text()
        for key in keys:
            assert f"<!-- credential:{key} -->" in source
    assert 'id="rules-action"' in guide("access-lists", language)[0]


def test_documentation_authenticated_localized_and_safe(client, admin, monkeypatch, tmp_path):
    assert client.get("/ui/documentation", follow_redirects=False).status_code == 200  # same logged-in client
    response = admin.get("/ui/documentation/proxy-hosts")
    assert response.status_code == 200
    assert "Доступность и SSL" in response.text
    admin.cookies.set("apm_language", "en")
    response = admin.get("/ui/documentation/certificates")
    assert "Status, reissuance and replacement" in response.text
    assert "guide-layout" in response.text
    assert admin.get("/ui/documentation/nonexistent").status_code == 404
    # Raw HTML in a packaged article must not become executable HTML.
    (tmp_path / "en").mkdir()
    (tmp_path / "en/index.md").write_text("# Guide\n\n<script>alert(1)</script>\n")
    monkeypatch.setattr("apm.documentation.ROOT", tmp_path)
    html, _ = guide("index", "en")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_documentation_requires_login(client):
    response = client.get("/ui/documentation", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_operations_share_context_translations_and_technical_details(admin):
    admin.post(
        "/api/v1/resources/proxy-hosts", json={"name": "My host", "data": {"domains": ["example.com"]}}
    )
    operation = admin.get("/api/v1/operations").json()[0]
    assert operation["title"] == "Применение изменений «My host»"
    assert operation["status_label"] == "В очереди"
    fragment = admin.get("/fragments/operations").text
    assert operation["title"] in fragment
    assert operation["message"] in fragment
    admin.cookies.set("apm_language", "en")
    operation = admin.get("/api/v1/operations").json()[0]
    assert operation["title"] == "Apply configuration changes «My host»"
