"""Exercise the real Tabler UI against a running local development instance."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18181")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disable-gpu"])
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
        page.locator('#editor button[type="submit"]').click()
        page.wait_for_selector("dialog[open]", state="hidden")
        page.get_by_text("Browser route", exact=True).wait_for()
        page.screenshot(path=str(args.output / "hosts.png"), full_page=True)
        page.get_by_text("Изменить", exact=True).first.click()
        page.wait_for_selector("dialog[open]")
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
        page.get_by_role("tab", name="Основное", exact=True).click()
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
        assert not errors, errors
        assert not network, network
        print(
            "Browser checks passed: create/edit proxy hosts and static/PHP sites, locations, HTTP/DNS certificates, parameter help, Escape/focus, no checkbox or form side effects, mobile bounds, dark theme, RU/EN; no JS/HTTP errors"
        )
        browser.close()


if __name__ == "__main__":
    main()
