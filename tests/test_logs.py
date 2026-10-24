import json
from datetime import datetime

import pytest

from apm.logs import LogQuery, query_logs


def write_access(config, entries):
    (config.data_dir / "logs/access.log").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )


def access(**changes):
    return {
        "time": "2026-10-25T10:30:00+03:00", "host": "app.example.com", "ip": "192.0.2.42",
        "method": "GET", "path": "/api/Привет", "status": 502, **changes,
    }


def test_access_filters_combine_and_search_decoded_unicode(admin, config):
    expected = access()
    write_access(config, [
        expected, access(status=200), access(method="POST"), access(host="other.test"),
        access(ip="198.51.100.2"), access(time="2026-10-25T11:30:00+03:00"), access(path="/health"),
    ])
    response = admin.get("/api/v1/logs/access", params={
        "q": "ПРИВЕТ", "host": "APP.EXAMPLE", "ip": "192.0.2.", "method": "get", "status": "5xx",
        "since": "2026-10-25T07:00:00Z", "until": "2026-10-25T08:00:00Z",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["entries"] == [expected]
    assert result["matched"] == 1
    assert result["scanned"] == 7
    assert result["exists"] and not result["truncated"]
    assert len(admin.get("/api/v1/logs/access", params={"status": "502"}).json()["entries"]) == 6


def test_search_precedes_limit_and_pagination_returns_newest_first(admin, config):
    write_access(config, [access(path=f"/older/{index}") for index in range(5)]
                 + [access(path="/recent") for _ in range(240)])
    params = {"q": "/older/", "limit": 2}
    first = admin.get("/api/v1/logs/access", params=params).json()
    assert [entry["path"] for entry in first["entries"]] == ["/older/4", "/older/3"]
    assert first["matched"] == 5 and first["has_more"]
    second = admin.get("/api/v1/logs/access", params={**params, "offset": 2}).json()
    assert [entry["path"] for entry in second["entries"]] == ["/older/2", "/older/1"]
    last = admin.get("/api/v1/logs/access", params={**params, "offset": 4}).json()
    assert [entry["path"] for entry in last["entries"]] == ["/older/0"]
    assert not last["has_more"]


def test_error_log_levels_search_and_context_filters(admin, config):
    path = config.data_dir / "logs/error.log"
    line = ('2026/10/25 12:34:56 [error] 123#456: *7 connect() failed (111: Connection refused), '
            'client: 192.0.2.1, server: app.example.com, request: "GET /api HTTP/1.1", '
            'upstream: "http://127.0.0.1:9000/api", host: "app.example.com"')
    path.write_text(line + "\n2026/10/25 12:35:00 [warn] 123#456: a warning\n", encoding="utf-8")
    params = {"level": "error", "q": "CONNECTION REFUSED", "host": "APP.EXAMPLE", "ip": "192.0.2.", "method": "GET"}
    response = admin.get("/api/v1/logs/error", params=params)
    assert response.status_code == 200, response.text
    entry = response.json()["entries"][0]
    assert entry["time"] == "2026/10/25 12:34:56" and entry["level"] == "error"
    assert entry["host"] == "app.example.com" and entry["ip"] == "192.0.2.1"
    assert "connect() failed" in entry["message"]
    assert admin.get("/api/v1/logs/error", params={"q": ".*"}).json()["matched"] == 0
    # Angie error timestamps have no offset and use the server's local time.
    at = datetime(2026, 10, 25, 12, 34, 56).astimezone().isoformat()
    assert admin.get("/api/v1/logs/error", params={"since": at, "until": at}).json()["matched"] == 1


def test_missing_empty_malformed_and_rotated_files(admin, config):
    url = "/api/v1/logs/access"
    result = admin.get(url).json()
    assert result["entries"] == [] and not result["exists"]
    path = config.data_dir / "logs/access.log"
    path.touch()
    assert admin.get(url).json()["exists"]
    path.write_bytes(b'broken line\n[]\nnull\n{"message":"<script>alert(1)</script>"}\n\xff\n')
    result = admin.get(url).json()
    assert result["scanned"] == 5 and result["matched"] == 5
    assert result["entries"][0] == {"message": "\ufffd"}
    assert result["entries"][1]["message"] == "<script>alert(1)</script>"
    assert admin.get(url, params={"since": "2026-01-01T00:00:00Z"}).json()["entries"] == []
    path.rename(path.with_name("access.log.1"))
    assert not admin.get(url).json()["exists"]


def test_query_is_bounded_and_discards_partial_first_line(tmp_path, monkeypatch):
    path = tmp_path / "access.log"
    path.write_text("first record is outside window\nsecond record\nlast record\n")
    monkeypatch.setattr("apm.logs.MAX_BYTES", 30)
    result = query_logs(path, "access", LogQuery())
    assert result["truncated"] and result["scanned"] == 2
    assert [entry["message"] for entry in result["entries"]] == ["last record", "second record"]
    monkeypatch.setattr("apm.logs.MAX_LINES", 1)
    result = query_logs(path, "access", LogQuery())
    assert result["truncated"] and result["scanned"] == 1


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 501}, {"offset": -1}, {"offset": 10001}, {"q": "a" * 501},
    {"status": "999"}, {"status": "5.*"}, {"level": "fatal"}, {"since": "invalid"},
    {"since": "2026-10-26T00:00:00Z", "until": "2026-10-25T00:00:00Z"},
])
def test_invalid_log_filters_are_rejected(admin, params):
    response = admin.get("/api/v1/logs/access", params=params)
    assert response.status_code == 422, response.text


def test_log_endpoints_require_login(client):
    for kind in ("access", "error"):
        assert client.get(f"/api/v1/logs/{kind}").status_code == 401


@pytest.mark.parametrize("role", ["observer", "operator"])
def test_error_log_remains_administrator_only(admin, role):
    response = admin.post("/api/v1/users", json={
        "email": f"{role}@example.com", "password": "test-password-12345", "role": role,
    })
    assert response.status_code == 201
    assert admin.post("/api/v1/auth/login", json={
        "email": f"{role}@example.com", "password": "test-password-12345",
    }).status_code == 200
    assert admin.get("/api/v1/logs/access").status_code == 200
    assert admin.get("/api/v1/logs/error").status_code == 403
    assert admin.get("/api/v1/logs/analytics").status_code == 404


def test_unreadable_log_is_reported_without_exposing_server_path(admin, monkeypatch):
    def fail(*args):
        raise PermissionError("/private/server/path")

    monkeypatch.setattr("apm.main.query_logs", fail)
    response = admin.get("/api/v1/logs/access")
    assert response.status_code == 503
    assert "/private" not in response.text
