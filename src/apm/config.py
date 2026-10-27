from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from apm.safety import SafetyCheck


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APM_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    database_url: str | None = None
    cookie_secure: bool = True
    session_seconds: int = 43200
    agent_socket: Path | None = None
    angie_binary: str = "angie"
    angie_mode: Literal["managed", "existing"] = "managed"
    angie_config: Path | None = None
    angie_prefix: Path | None = None
    angie_status_url: str = "http://127.0.0.1:18081/status/angie"
    backend_url: str = "http://127.0.0.1:8181"
    admin_listen: str = "0.0.0.0:81"
    safe_apply: bool = True
    safe_apply_timeout: int = 120
    safe_apply_checks: list[SafetyCheck] = []
    default_language: str = "ru"
    docker_url: str = "http://docker-gateway:2375"
    discovery_enabled: bool = False
    discovery_networks: list[str] = []
    discovery_domains: list[str] = []
    discovery_acme_terms_agreed: bool = False
    acme_email: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret_file: Path | None = None
    public_url: str = "https://localhost:81"
    oidc_only: bool = False
    certbot_binary: str = "certbot"
    acme_server: str = "https://acme-v02.api.letsencrypt.org/directory"
    metrics_retention_days: int = 7
    pre_run_dir: Path = Path("/etc/apm/pre-run.d")
    development: bool = False

    @model_validator(mode="after")
    def existing_angie_paths(self):
        if not 30 <= self.safe_apply_timeout <= 600:
            raise ValueError("APM_SAFE_APPLY_TIMEOUT must be between 30 and 600 seconds")
        if len(self.safe_apply_checks) > 32:
            raise ValueError("At most 32 APM_SAFE_APPLY_CHECKS are allowed")
        names = [check.name for check in self.safe_apply_checks]
        if "APM" in names or len(names) != len(set(names)):
            raise ValueError("Safe apply check names must be unique; APM is reserved for the panel")
        if self.angie_mode == "existing":
            for name in ("data_dir", "angie_config", "angie_prefix"):
                path = getattr(self, name)
                if path is None or not path.is_absolute():
                    raise ValueError(f"Existing Angie requires an absolute APM_{name.upper()}")
        return self

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir.resolve() / 'apm.sqlite3'}"

    @property
    def socket(self) -> Path:
        return self.agent_socket or self.data_dir / "run/agent.sock"

    @property
    def root_config(self) -> Path:
        return self.angie_config or self.data_dir / "angie.conf"

    def prepare(self) -> None:
        self.data_dir = self.data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
        for name in ("run", "revisions", "certificates", "acme", "webroot", "logs", "exports", "sites"):
            (self.data_dir / name).mkdir(exist_ok=True, mode=0o750)
        (self.data_dir / "reports").mkdir(exist_ok=True, mode=0o750)


settings = Settings()
