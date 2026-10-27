"""Exercise the real Tabler UI against a running local development instance."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import select

from apm.agent import bootstrap_certificate
from apm.config import Settings
from apm.db import Database, Job


def check_safety(page, args):
    state = {"available": True, "status": "awaiting_confirmation", "halted": False,
             "enabled": True, "watchdog_independent": True, "timeout_seconds": 120,
             "revision_id": "11111111-1111-4111-8111-111111111111", "token": "browser-test-token-only",
             "seconds_remaining": 120, "can_manage": True, "route_verified": True,
             "checks": [{"name": "APM", "ok": True}, {"name": "Portal", "ok": True}]}
    actions = []
    page.route("**/api/v1/safety", lambda route: route.fulfill(json=state))
    def finish(route):
        actions.append((route.request.url.rsplit("/", 1)[-1], route.request.post_data_json))
        state["status"] = "applied" if actions[-1][0] == "confirm" else "rolled_back"
        state["halted"] = actions[-1][0] == "rollback"
        route.fulfill(json={"status": state["status"]})
    page.route("**/api/v1/safety/*", finish)
    page.goto(args.url + "/ui/operations")
    box = page.locator("#safety-notice")
    confirm = box.get_by_role("button", name="Confirm access", exact=True)
    expect(confirm).to_be_enabled()
    expect(page.locator("#safety-countdown")).to_contain_text(":")
    state["checks"][1]["ok"] = False
    page.evaluate("safetyStatus()")
    expect(confirm).to_be_disabled()
    state["checks"][1]["ok"] = True
    state["route_verified"] = False
    page.evaluate("safetyStatus()")
    expect(confirm).to_be_disabled()
    expect(box).to_contain_text("candidate Angie listener")
    state["route_verified"] = True
    page.evaluate("safetyStatus()")
    expect(confirm).to_be_enabled()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(args.output / "safety-trial-mobile.png"), full_page=True)
    confirm.click()
    expect(box).to_contain_text("Safe mode enabled")
    assert actions[-1] == ("confirm", {"revision_id": state["revision_id"], "token": state["token"]})
    state["status"] = "awaiting_confirmation"
    page.evaluate("safetyStatus()")
    box.get_by_role("button", name="Roll back now", exact=True).click()
    expect(box).to_contain_text("applies are paused")
    assert actions[-1][0] == "rollback"
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.screenshot(path=str(args.output / "safety-halted.png"), full_page=True)
    state.update(status="applied", halted=False, enabled=False)
    page.evaluate("safetyStatus()")
    expect(box).to_contain_text("Safe mode disabled")
    state.update(enabled=True, watchdog_independent=False)
    page.evaluate("safetyStatus()")
    expect(box).to_contain_text("independent watchdog is not running")
    state.update(available=False, reason="agent_upgrade_required")
    page.evaluate("safetyStatus()")
    expect(box).to_contain_text("Update its installed package")
    page.unroute("**/api/v1/safety")
    page.unroute("**/api/v1/safety/*")


def check_logs(page, args):
    directory = args.data / "logs"
    directory.mkdir(exist_ok=True)
    records = [
        {"time": "2026-10-25T10:30:00+03:00", "host": "browser.example.com", "ip": "192.0.2.42",
         "method": "GET", "path": f"/api/needle/{index}", "status": 502}
        for index in range(61)
    ] + [
        {"time": "2026-10-25T10:31:00+03:00", "host": "other.example.com", "ip": "198.51.100.1",
         "method": "POST", "path": "/health", "status": 200},
        {"message": '<img src=x onerror="alert(1)">'},
    ]
    (directory / "access.log").write_text("".join(json.dumps(record) + "\n" for record in records))
    error_path = directory / "error.log"
    error_path.write_text(
        '2026/10/25 10:30:00 [error] 123#456: connection refused, client: 192.0.2.42, '
        'request: "GET /api HTTP/1.1", host: "browser.example.com"\n'
        '2026/10/25 10:31:00 [warn] 123#456: upstream timed out\n'
    )
    page.goto(args.url + "/ui/logs")
    expect(page.locator(".log-table tbody tr")).to_have_count(63)
    assert page.locator(".log-table img").count() == 0
    assert '<img src=x onerror="alert(1)">' in page.locator(".log-table").inner_text()
    for key, value in [("q", "NEEDLE"), ("host", "BROWSER.EXAMPLE"), ("ip", "192.0.2."), ("status", "5xx")]:
        page.locator(f"#log-{key}").fill(value)
    page.locator("#log-method").select_option("GET")
    page.locator("#log-limit").select_option("50")
    page.locator('#log-filters button[type="submit"]').click()
    expect(page.locator(".log-table tbody tr")).to_have_count(50)
    expect(page.locator(".log-table tbody tr").first).to_contain_text("/api/needle/60")
    page.locator("#log-older").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(11)
    expect(page.locator("#log-older")).to_be_disabled()
    page.reload()
    expect(page.locator(".log-table tbody tr")).to_have_count(11)
    assert page.locator("#log-q").input_value() == "NEEDLE"
    page.locator("#refresh").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(11)
    page.locator("#log-newer").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(50)
    page.screenshot(path=str(args.output / "logs-access.png"), full_page=True)
    page.locator("#log-q").fill("no-matching-record")
    page.locator("#log-q").press("Enter")
    expect(page.locator(".empty-state")).to_contain_text("Записей по этим фильтрам нет")
    page.locator("#log-reset").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(63)
    page.locator("#log-kind").select_option("error")
    expect(page.locator(".log-table tbody tr")).to_have_count(2)
    assert page.locator("#log-status").is_hidden() and page.locator("#log-level").is_visible()
    page.locator("#log-level").select_option("error")
    page.locator('#log-filters button[type="submit"]').click()
    expect(page.locator(".log-table tbody tr")).to_have_count(1)
    expect(page.locator(".log-table")).to_contain_text("connection refused")
    page.screenshot(path=str(args.output / "logs-error.png"), full_page=True)
    page.locator("#log-auto").check()
    with error_path.open("a") as stream:
        stream.write("2026/10/25 10:32:00 [error] 123#456: new auto refresh record\n")
    expect(page.locator(".log-table tbody tr")).to_have_count(2, timeout=10000)
    page.locator("#log-auto").uncheck()
    # Rotation can remove every record on the current older page.
    page.locator("#log-kind").select_option("access")
    page.locator("#log-reset").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(63)
    page.locator("#log-limit").select_option("50")
    page.locator('#log-filters button[type="submit"]').click()
    expect(page.locator(".log-table tbody tr")).to_have_count(50)
    page.locator("#log-older").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(13)
    (directory / "access.log").write_text(json.dumps(records[0]) + "\n")
    page.locator("#refresh").click()
    expect(page.locator(".log-table tbody tr")).to_have_count(1)
    expect(page.locator("#log-newer")).to_be_disabled()
    expect(page.locator(".log-table")).to_contain_text("/api/needle/0")
    page.locator("#log-kind").select_option("error")
    expect(page.locator(".log-table tbody tr")).to_have_count(3)
    page.locator("#log-level").select_option("error")
    page.locator('#log-filters button[type="submit"]').click()
    expect(page.locator(".log-table tbody tr")).to_have_count(2)
    page.locator("#language-switch").click()
    expect(page.locator("h1")).to_have_text("Angie logs")
    expect(page.locator(".log-table")).to_contain_text("connection refused")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#theme-switch").click()
    page.screenshot(path=str(args.output / "logs-mobile-dark.png"), full_page=True)
    page.locator("#theme-switch").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#language-switch").click()
    expect(page.locator("h1")).to_have_text("Журналы Angie")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18181")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--disable-gpu"],
            executable_path=str(args.browser_executable) if args.browser_executable else None,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, network = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: (
                network.append((response.status, response.url)) if response.status >= 400 else None
            ),
        )
        page.goto(args.url + "/login")
        page.screenshot(path=str(args.output / "setup.png"), full_page=True)
        token = args.data / "setup.token"
        if token.exists():
            page.locator('[name="token"]').fill(token.read_text().strip())
            page.locator('[name="email"]').fill("browser@example.com")
            page.locator('[name="password"]').fill("browser-test-password-12345")
            page.locator('button[type="submit"]:visible').click()
        else:
            page.locator('[name="email"]').fill("browser@example.com")
            page.locator('[name="password"]').fill("browser-test-password-12345")
            page.locator('button[type="submit"]:visible').click()
        page.wait_for_url("**/ui/dashboard")
        page.wait_for_selector(".dashboard-grid")
        page.screenshot(path=str(args.output / "dashboard.png"), full_page=True)
        check_logs(page, args)
        page.goto(args.url + "/ui/proxy-hosts")
        page.locator("#create").click()
        page.wait_for_selector("dialog[open]")
        page.screenshot(path=str(args.output / "create-host.png"), full_page=True)
        # Form controls are schema driven; scope by their field wrappers.
        assert page.get_by_role("tab").all_text_contents() == ["Основное", "Пути", "SSL", "Дополнительно"]
        page.locator("#editor-name").fill("Browser route")
        domain = (
            page.locator(".schema-field").filter(has=page.locator("label", has_text="Доменные имена")).first
        )
        domain.locator("textarea").fill("browser.example.com")
        fields = page.locator("#editor .schema-field[data-field]")
        for field in fields.all():
            if field.get_attribute("data-field"):
                assert field.locator(":scope > .field-help-button").count() == 1
                assert field.locator(":scope > .field-help-popup p").text_content().strip()
        domain.locator(".field-help-button").click()
        assert domain.locator(".field-help-popup").is_visible()
        assert "app.example.com" in domain.locator(".field-help-popup").inner_text()
        assert domain.locator(".field-help-button").get_attribute("aria-expanded") == "true"
        page.screenshot(path=str(args.output / "field-help.png"), full_page=True)
        page.keyboard.press("Escape")
        assert domain.locator(".field-help-popup").is_hidden()
        assert page.locator("dialog[open]").count() == 1
        assert domain.locator("textarea").input_value() == "browser.example.com"
        assert domain.locator(".field-help-button").evaluate("node => document.activeElement === node")
        backend_help = page.get_by_role("button", name="Помощь: Адрес backend", exact=True)
        backend_help.focus()
        backend_help.press("Enter")
        backend_popup = page.locator('[data-field="host"] > .field-help-popup')
        assert backend_popup.is_visible()
        assert "host.docker.internal" in backend_popup.inner_text()
        domain.locator(".field-help-button").click()
        assert backend_popup.is_hidden()
        domain.locator("textarea").click()
        assert domain.locator(".field-help-popup").is_hidden()
        backend_scheme = page.locator('#proxy-panel-details [data-field="scheme"] select')
        backend_verify = page.locator('[data-field="upstream_verify"] input')
        assert backend_verify.is_hidden()
        backend_scheme.select_option("https")
        assert backend_verify.is_visible() and backend_verify.is_checked()
        assert "самоподписанным" in page.locator("#proxy-panel-details").inner_text()
        backend_verify.uncheck()
        page.locator('[data-field="upstream_sni"] input').fill("backend.example.test")
        backend_scheme.select_option("http")
        assert backend_verify.is_hidden()
        backend_scheme.select_option("grpcs")
        assert backend_verify.is_visible() and not backend_verify.is_checked()
        backend_scheme.select_option("grpc")
        assert backend_verify.is_hidden()
        backend_scheme.select_option("https")
        page.screenshot(path=str(args.output / "proxy-backend-tls.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#editor").evaluate("node => node.scrollWidth <= node.clientWidth")
        backend_verify.scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / "proxy-backend-tls-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator('#editor button[type="submit"]').click()
        page.wait_for_selector("dialog[open]", state="hidden")
        page.get_by_text("Browser route", exact=True).wait_for()
        route_link = page.get_by_role("link", name="Browser route", exact=True)
        assert route_link.get_attribute("href") == "http://browser.example.com/"
        assert page.locator('[data-health-status="unknown"]').count() == 1
        page.screenshot(path=str(args.output / "hosts.png"), full_page=True)
        page.get_by_text("Изменить", exact=True).first.click()
        page.wait_for_selector("dialog[open]")
        assert backend_scheme.input_value() == "https"
        assert backend_verify.is_visible() and not backend_verify.is_checked()
        assert page.locator('[data-field="upstream_sni"] input').input_value() == "backend.example.test"
        backend_scheme.select_option("http")
        page.locator("#editor-name").fill("Browser route edited")
        page.get_by_role("tab", name="Дополнительно", exact=True).click()
        page.locator('[data-field="timeout_seconds"] input').fill("123")
        page.get_by_role("tab", name="Пути", exact=True).click()
        locations = page.locator('[data-field="locations"]')
        locations.get_by_role("button", name="＋", exact=True).click()
        locations.locator('[data-field="path"] input').fill("/api")
        location_help = locations.locator('[data-field="path"] > .field-help-button')
        location_help.click()
        assert locations.locator('[data-field="path"] > .field-help-popup').is_visible()
        page.get_by_role("button", name="Закрыть справку", exact=True).click()
        assert locations.locator('[data-field="path"] input').input_value() == "/api"
        locations.locator('[data-field="port"] input').fill("8090")
        locations.locator('[data-field="scheme"] select').select_option("https")
        page.get_by_role("tab", name="Основное", exact=True).click()
        assert backend_verify.is_visible() and not backend_verify.is_checked()
        page.get_by_role("tab", name="Пути", exact=True).click()
        locations.get_by_role("button", name="×", exact=True).click()
        page.get_by_role("tab", name="Основное", exact=True).click()
        assert backend_verify.is_hidden()
        page.get_by_role("tab", name="Пути", exact=True).click()
        locations.get_by_role("button", name="＋", exact=True).click()
        locations.locator('[data-field="path"] input').fill("/api")
        locations.locator('[data-field="port"] input').fill("8090")
        locations.locator('[data-field="scheme"] select').select_option("grpcs")
        page.get_by_role("tab", name="Основное", exact=True).click()
        assert backend_verify.is_visible() and not backend_verify.is_checked()
        assert page.locator("#editor-name").input_value() == "Browser route edited"
        page.locator('#editor button[type="submit"]').click()
        page.get_by_text("Browser route edited", exact=True).wait_for()

        def resources(kind):
            response = page.request.get(args.url + "/api/v1/resources/" + kind)
            assert response.ok, response.text()
            return response.json()

        route = resources("proxy-hosts")[0]
        assert route["data"]["timeout_seconds"] == 123
        assert route["data"]["locations"][0]["path"] == "/api"
        assert route["data"]["locations"][0]["port"] == 8090
        assert route["data"]["locations"][0]["scheme"] == "grpcs"
        assert route["data"]["upstream_verify"] is False
        assert route["data"]["upstream_sni"] == "backend.example.test"

        # All certificate requests stay queued: this isolated UI server has no worker.
        page.locator("#create").click()
        page.locator("#editor-name").fill("Browser SSL HTTP")
        page.locator('[data-field="domains"] textarea').fill("ssl.example.test")
        page.get_by_role("tab", name="SSL", exact=True).click()
        page.locator('[data-field="certificate_id"] select').select_option("new")
        assert page.locator('[data-field="tls"] select').input_value() == "http"
        assert page.locator('[data-field="acme_email"] input').input_value() == "browser@example.com"
        terms = page.locator('[data-field="acme_terms_agreed"] input')
        page.locator('[data-field="acme_terms_agreed"] > .field-help-button').click()
        assert not terms.is_checked()
        page.get_by_role("button", name="Закрыть справку", exact=True).click()
        page.get_by_role("tab", name="Основное", exact=True).click()
        page.locator("#editor-save").click()
        assert page.get_by_role("tab", name="SSL", exact=True).get_attribute("aria-selected") == "true"
        assert page.locator("dialog[open]").count() == 1
        page.locator('[data-field="acme_terms_agreed"] input').check()
        page.screenshot(path=str(args.output / "proxy-ssl.png"), full_page=True)
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        page.get_by_text("Browser SSL HTTP", exact=True).wait_for()
        http_host = next(r for r in resources("proxy-hosts") if r["name"] == "Browser SSL HTTP")
        certificate_id = http_host["data"]["certificate_id"]
        assert certificate_id and http_host["data"]["tls"] == "http"
        assert len(resources("certificates")) == 1
        row = page.locator("tr").filter(has=page.get_by_text("Browser SSL HTTP", exact=True))
        row.get_by_role("button", name="Изменить", exact=True).click()
        page.get_by_role("tab", name="SSL", exact=True).click()
        assert page.locator('[data-field="certificate_id"] select').input_value() == certificate_id
        assert page.locator('[data-field="acme_email"]').is_hidden()
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        assert len(resources("certificates")) == 1

        csrf = page.locator('meta[name="csrf-token"]').get_attribute("content")
        profile = page.request.post(
            args.url + "/api/v1/resources/dns-profiles",
            headers={"X-CSRF-Token": csrf},
            data={"name": "Browser DNS", "data": {"provider": "regru", "zone": "example.test"}},
        )
        assert profile.status == 201, profile.text()
        page.locator("#create").click()
        page.locator("#editor-name").fill("Browser SSL DNS")
        page.locator('[data-field="domains"] textarea').fill("*.example.test")
        page.get_by_role("tab", name="SSL", exact=True).click()
        page.locator('[data-field="certificate_id"] select').select_option("new")
        assert page.locator('[data-field="tls"] select').input_value() == "dns"
        page.locator('[data-field="dns_profile_id"] select').select_option(profile.json()["id"])
        page.locator('[data-field="acme_terms_agreed"] input').check()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.output / "proxy-ssl-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#editor").evaluate("node => node.scrollWidth <= node.clientWidth")
        page.locator('[data-field="dns_profile_id"] > .field-help-button').click()
        help_popup = page.locator('[data-field="dns_profile_id"] > .field-help-popup')
        bounds = help_popup.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0
        assert bounds["x"] + bounds["width"] <= 390
        assert bounds["y"] + bounds["height"] <= 844
        page.screenshot(path=str(args.output / "field-help-mobile.png"), full_page=True)
        page.keyboard.press("Escape")
        assert page.locator("dialog[open]").count() == 1
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        dns_host = next(r for r in resources("proxy-hosts") if r["name"] == "Browser SSL DNS")
        certificate = next(
            r for r in resources("certificates") if r["id"] == dns_host["data"]["certificate_id"]
        )
        assert certificate["data"]["mode"] == "dns"
        assert certificate["data"]["dns_profile_id"] == profile.json()["id"]

        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(args.url + "/ui/sites")
        page.locator("#create").click()
        page.locator("#editor-name").fill("Browser static site")
        page.locator('[data-field="domains"] textarea').fill("static.example.test")
        page.get_by_role("textbox", name="Каталог сайта", exact=False).fill("company")
        page.get_by_role("textbox", name="Адрес PHP-FPM", exact=True).fill("php-fpm:9000")
        site_fields = page.locator("#editor .schema-field[data-field]")
        assert site_fields.count() == 8
        for field in site_fields.all():
            help_button = field.locator(":scope > .field-help-button")
            assert help_button.count() == 1
            help_button.click()
            popup = field.locator(":scope > .field-help-popup")
            assert popup.is_visible()
            assert popup.locator("p").text_content().strip()
            assert page.locator("dialog[open]").count() == 1
            page.keyboard.press("Escape")
            assert popup.is_hidden()
            assert help_button.evaluate("node => document.activeElement === node")
        assert page.locator("#editor-enabled").is_checked()
        assert not page.locator('[data-field="directory_index"] input').is_checked()
        assert not page.locator('[data-field="fancyindex"] input').is_checked()
        assert page.locator("#editor-name").input_value() == "Browser static site"
        assert page.locator('[data-field="root_id"] input').input_value() == "company"
        assert page.locator('[data-field="php_upstream"] input').input_value() == "php-fpm:9000"
        page.locator('[data-field="root_id"] > .field-help-button').click()
        root_help = page.locator('[data-field="root_id"] > .field-help-popup')
        assert "/data/sites/company" in root_help.inner_text()
        assert "index.html" in root_help.inner_text()
        page.screenshot(path=str(args.output / "sites-help-directory.png"), full_page=True)
        page.keyboard.press("Escape")
        page.locator('[data-field="certificate_id"] > .field-help-button').click()
        certificate_help = page.locator('[data-field="certificate_id"] > .field-help-popup')
        assert "HTTP 503" in certificate_help.inner_text()
        assert "странице «Сертификаты»" in certificate_help.inner_text()
        assert "прокси-хоста" not in certificate_help.inner_text()
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('[data-field="php_upstream"] > .field-help-button').click()
        php_help = page.locator('[data-field="php_upstream"] > .field-help-popup')
        assert "одинаковому абсолютному пути" in php_help.inner_text()
        assert "исходный текст" in php_help.inner_text()
        bounds = php_help.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0
        assert bounds["x"] + bounds["width"] <= 390
        assert bounds["y"] + bounds["height"] <= 844
        assert page.locator("#editor").evaluate("node => node.scrollWidth <= node.clientWidth")
        page.screenshot(path=str(args.output / "sites-help-php-mobile.png"))
        page.keyboard.press("Escape")
        assert page.locator("dialog[open]").count() == 1
        page.locator('[data-field="directory_index"] input').check()
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        site = resources("sites")[0]
        assert site["data"]["root_id"] == "company"
        assert site["data"]["php_upstream"] == "php-fpm:9000"
        assert site["data"]["directory_index"] is True
        assert site["data"]["fancyindex"] is False
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Изменить", exact=True).click()
        page.locator('[data-field="php_upstream"] > .field-help-button').click()
        assert php_help.is_visible()
        assert page.locator('[data-field="php_upstream"] input').input_value() == "php-fpm:9000"
        page.keyboard.press("Escape")
        page.locator("#editor-name").fill("Browser static site edited")
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        assert resources("sites")[0]["name"] == "Browser static site edited"

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(args.url + "/ui/dashboard")
        page.wait_for_selector(".dashboard-grid")
        page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(args.url + "/ui/proxy-hosts")
        page.locator("#theme-switch").click()
        page.locator("#create").click()
        page.locator('[data-field="host"] > .field-help-button').click()
        page.screenshot(path=str(args.output / "field-help-dark.png"), full_page=True)
        page.keyboard.press("Escape")
        page.locator("#editor-close").click()
        page.locator("#language-switch").click()
        page.get_by_role("heading", name="Proxy hosts", exact=True).wait_for()
        page.locator("#create").click()
        page.get_by_role("button", name="Help: Backend host", exact=True).click()
        assert (
            "Application IP address" in page.locator('[data-field="host"] > .field-help-popup').inner_text()
        )
        page.get_by_role("button", name="Close help", exact=True).click()
        backend_scheme.select_option("https")
        assert backend_verify.is_visible() and backend_verify.is_checked()
        assert "self-signed" in page.locator("#proxy-panel-details").inner_text()
        page.locator("#editor-cancel").click()
        page.goto(args.url + "/ui/sites")
        page.get_by_role("button", name="Edit", exact=True).click()
        page.wait_for_selector("dialog[open]")
        assert page.locator("#editor .field-help-button").count() == 8
        page.get_by_role("button", name="Help: PHP-FPM address", exact=True).click()
        assert "same absolute path" in php_help.inner_text()
        assert "source text" in php_help.inner_text()
        page.screenshot(path=str(args.output / "sites-help-en-dark.png"), full_page=True)
        page.get_by_role("button", name="Close help", exact=True).click()
        page.get_by_role("button", name="Help: SSL certificate", exact=True).click()
        assert "Certificates page" in certificate_help.inner_text()
        assert "proxy host" not in certificate_help.inner_text()
        page.keyboard.press("Escape")
        page.locator("#editor-cancel").click()
        # The server has no worker: queued requests must disable manual reissuance.
        page.goto(args.url + "/ui/certificates")
        page.locator('[data-action="renew"]').first.wait_for()
        assert page.locator('[data-action="renew"]').first.is_disabled()
        fixture_config = Settings(_env_file=None, data_dir=args.data)
        fixture_db = Database(fixture_config)
        with fixture_db.session() as session:
            for job in session.scalars(select(Job).where(Job.kind == "certificate.issue")):
                job.status = "succeeded"
        page.locator("#refresh").click()
        expect(page.locator('[data-action="renew"]').first).to_be_enabled()
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/renew")) as renewal:
            page.locator('[data-action="renew"]').first.click()
        assert renewal.value.status == 202
        assert renewal.value.json()["operation_id"]
        expect(page.locator('[data-action="renew"]').first).to_be_disabled()
        with fixture_db.session() as session:
            forced = [job for job in session.scalars(select(Job).where(Job.kind == "certificate.issue"))
                      if job.payload.get("force")]
            assert len(forced) == 1
        page.screenshot(path=str(args.output / "certificates.png"), full_page=True)
        # Upload actual local PEM material and check visible validity dates.
        bootstrap_certificate(fixture_config)
        created = page.request.post(args.url + "/api/v1/resources/certificates",
            headers={"X-CSRF-Token": csrf},
            data={"name": "Uploaded certificate", "data": {"mode": "custom", "domains": ["localhost"]}})
        assert created.status == 201
        page.locator("#refresh").click()
        cert_row = page.locator("tr").filter(has=page.get_by_text("Uploaded certificate", exact=True))
        cert_row.get_by_role("button", name="Upload", exact=True).click()
        page.locator('#editor input[type="file"]').nth(0).set_input_files(str(args.data / "bootstrap/fullchain.pem"))
        page.locator('#editor input[type="file"]').nth(1).set_input_files(str(args.data / "bootstrap/privkey.pem"))
        page.locator("#editor-save").click()
        page.wait_for_selector("dialog[open]", state="hidden")
        cert_row.locator('[data-certificate-status="valid"]').wait_for()
        assert "Valid until" in cert_row.inner_text()
        assert cert_row.locator('[data-action="renew"]').count() == 0
        page.screenshot(path=str(args.output / "certificates.png"), full_page=True)
        page.goto(args.url + "/ui/operations")
        page.get_by_text("Reissue certificate", exact=False).first.wait_for()
        assert "waiting for an available worker" in page.locator("#content").inner_text()
        page.screenshot(path=str(args.output / "operations.png"), full_page=True)
        page.goto(args.url + "/ui/access-lists")
        page.locator("#create").click()
        page.locator('[data-field="satisfy"] > .field-help-button').click()
        assert "both the IP rules" in page.locator('[data-field="satisfy"] > .field-help-popup').inner_text()
        assert "replaces the entire set" in page.locator("#editor-fields").inner_text()
        page.keyboard.press("Escape")
        page.locator("#editor-cancel").click()
        page.goto(args.url + "/ui/documentation/access-lists")
        page.locator(".guide-article #satisfy").wait_for()
        assert "<!-- setting:" not in page.locator(".guide-article").inner_text()
        page.screenshot(path=str(args.output / "documentation-en.png"), full_page=True)
        page.locator("#language-switch").click()
        page.locator(".guide-article #satisfy").wait_for()
        assert "Пустое поле" in page.locator(".guide-article").inner_text()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(args.output / "documentation-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(args.url + "/ui/operations")
        if page.locator("html").get_attribute("lang") != "en":
            page.locator("#language-switch").click()
            expect(page.locator("html")).to_have_attribute("lang", "en")
        check_safety(page, args)
        fixture_db.engine.dispose()
        assert not errors, errors
        assert not network, network
        print(
            "Browser checks passed: safety countdown/confirmation/rollback, required checks and route identity, Angie access/error logs, search/filters/pagination/auto refresh, proxy links/availability, backend TLS verification/SNI persistence, locations, HTTP/DNS certificates, forced reissue/deduplication, PEM upload/validity dates, operation messages, ACL help, packaged RU/EN documentation, mobile/dark theme, Escape/focus; no JS/HTTP errors"
        )
        browser.close()


if __name__ == "__main__":
    main()
