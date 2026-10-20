import pytest
from fastapi.testclient import TestClient

from apm.config import Settings
from apm.main import create_app


@pytest.fixture
def config(tmp_path):
    value = Settings(data_dir=tmp_path / "data", cookie_secure=True)
    value.prepare()
    return value


@pytest.fixture
def client(config):
    with TestClient(create_app(config), base_url="https://testserver") as client:
        yield client


@pytest.fixture
def admin(client, config):
    result = client.post(
        "/api/v1/auth/setup",
        json={
            "email": "admin@example.com",
            "password": "test-password-12345",
            "token": (config.data_dir / "setup.token").read_text().strip(),
        },
    )
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return client
