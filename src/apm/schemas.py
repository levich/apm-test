import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def hostname(value: str) -> str:
    value = value.strip().rstrip(".")
    wildcard = value.startswith("*.")
    value = value[2:] if wildcard else value
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    value = value.encode("idna").decode().lower()
    if len(value) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in value.split(".")
    ):
        raise ValueError("Invalid hostname")
    return ("*." if wildcard else "") + value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Peer(Strict):
    host: str
    port: int = Field(default=80, ge=1, le=65535)
    weight: int = Field(default=1, ge=1, le=1000)
    backup: bool = False
    down: bool = False
    host_validator = field_validator("host")(hostname)


class Upstream(Strict):
    peers: list[Peer] = Field(min_length=1)
    strategy: Literal["round_robin", "least_conn", "ip_hash"] = "round_robin"

    @model_validator(mode="after")
    def compatible_backup(self):
        if self.strategy == "ip_hash" and any(peer.backup for peer in self.peers):
            raise ValueError("IP hash cannot use backup peers")
        return self


class Location(Strict):
    path: str = "/"
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    scheme: Literal["http", "https", "grpc", "grpcs"] = "http"
    upstream_id: str | None = None
    access_ids: list[str] = []
    access_mode: Literal["inherit", "replace", "public"] = "inherit"
    auth_provider_id: str | None = None
    strip_prefix: bool = False
    host_validator = field_validator("host")(hostname)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        if not re.fullmatch(r"/[A-Za-z0-9_./~%+@=,-]*", value) or ".." in value.split("/"):
            raise ValueError("Invalid location path")
        return value


class Route(Location):
    domains: list[str] = Field(min_length=1)
    tls: Literal["off", "http", "dns", "certificate"] = "off"
    certificate_id: str | None = None
    dns_profile_id: str | None = None
    acme_email: str = ""
    acme_terms_agreed: bool = False
    force_ssl: bool = True
    http2: bool = True
    http3: bool = False
    locations: list[Location] = []
    header_policy_id: str | None = None
    tls_policy_id: str | None = None
    client_ca_id: str | None = None
    geo_policy_id: str | None = None
    crowdsec_profile_id: str | None = None
    request_buffering: bool = True
    response_buffering: bool = True
    upstream_compression: bool = False
    upstream_verify: bool = True
    upstream_sni: str | None = None
    compression: Literal["off", "gzip", "brotli", "zstd"] = "off"
    rate: int = Field(default=0, ge=0, le=100000)
    connection_limit: int = Field(default=0, ge=0, le=100000)
    max_body_mb: int = Field(default=100, ge=1, le=100000)
    timeout_seconds: int = Field(default=60, ge=1, le=86400)
    noindex: bool = False
    blocked_user_agents: list[str] = []
    websocket: bool = True
    advanced: str = ""

    @field_validator("domains")
    @classmethod
    def domains_valid(cls, values):
        result = [hostname(v) for v in values]
        if len(set(result)) != len(result):
            raise ValueError("Duplicate domain")
        return result

    @model_validator(mode="after")
    def tls_parameters(self):
        if self.tls == "dns" and not self.dns_profile_id:
            raise ValueError("DNS profile required")
        if self.tls == "certificate" and not self.certificate_id:
            raise ValueError("Certificate required")
        if self.tls in ("http", "dns") and not self.acme_terms_agreed:
            raise ValueError("Explicit ACME terms agreement required")
        if self.tls == "http" and any(v.startswith("*.") for v in self.domains):
            raise ValueError("Wildcard requires DNS validation")
        if len({loc.path for loc in self.locations}) != len(self.locations):
            raise ValueError("Duplicate location")
        return self


class Redirect(Strict):
    domains: list[str] = Field(min_length=1)
    target: str
    code: Literal[301, 302, 307, 308] = 301
    preserve_uri: bool = True
    certificate_id: str | None = None

    @field_validator("domains")
    @classmethod
    def domain_names(cls, values):
        return [hostname(v) for v in values]

    @field_validator("target")
    @classmethod
    def target_valid(cls, value):
        if not re.fullmatch(r"https?://[^\s\"'{};$\\]+", value):
            raise ValueError("Expected an HTTP(S) redirect URL")
        return value


class Stream(Strict):
    listen_port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"
    host: str
    port: int = Field(ge=1, le=65535)
    upstream_id: str | None = None
    certificate_id: str | None = None
    upstream_tls: bool = False
    upstream_verify: bool = True
    upstream_sni: str | None = None
    proxy_protocol_in: bool = False
    proxy_protocol_out: bool = False
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    advanced: str = ""
    host_validator = field_validator("host")(hostname)

    @model_validator(mode="after")
    def stream_rules(self):
        if self.listen_port in (80, 81, 443, 8181, 18081):
            raise ValueError("Reserved control-plane or HTTP port")
        if self.protocol == "udp" and (self.certificate_id or self.upstream_tls or self.proxy_protocol_in):
            raise ValueError("UDP cannot use TCP TLS or incoming PROXY protocol")
        return self


class AccessRule(Strict):
    action: Literal["allow", "deny"]
    address: str

    @field_validator("address")
    @classmethod
    def address_valid(cls, value):
        return value if value == "all" else str(ipaddress.ip_network(value, strict=False))


class Access(Strict):
    rules: list[AccessRule] = []
    users: list[str] = []
    satisfy: Literal["all", "any"] = "all"
    pass_auth: bool = False

    @field_validator("users")
    @classmethod
    def users_valid(cls, values):
        if any(not re.fullmatch(r"[a-zA-Z0-9_.@-]{1,100}", v) for v in values):
            raise ValueError("Invalid Basic Auth username")
        return values


class Headers(Strict):
    response: dict[str, str] = {}
    upstream: dict[str, str] = {}
    remove: list[str] = []
    hsts: bool = False
    hsts_subdomains: bool = False
    frame_options: Literal["upstream", "DENY", "SAMEORIGIN", "remove"] = "upstream"

    @model_validator(mode="after")
    def names_valid(self):
        for name in [*self.response, *self.upstream, *self.remove]:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                raise ValueError("Invalid HTTP header name")
        return self


class TLS(Strict):
    protocols: list[Literal["TLSv1.2", "TLSv1.3"]] = ["TLSv1.2", "TLSv1.3"]
    ciphers: str = "HIGH:!aNULL:!MD5:!3DES"
    curves: str = "auto"
    ocsp: bool = False
    certificate_compression: bool = False
    ech_id: str | None = None

    @field_validator("protocols")
    @classmethod
    def nonempty(cls, values):
        if not values:
            raise ValueError("At least one TLS version required")
        return list(dict.fromkeys(values))


class DNSProfile(Strict):
    provider: Literal["webnames", "yandex", "regru", "selectel", "cloudru"]
    zone: str
    zone_id: str = ""
    ttl: int = Field(default=300, ge=60, le=86400)
    propagation_timeout: int = Field(default=600, ge=30, le=3600)
    discovery_allowed: bool = False
    operator_allowed: bool = False
    domain_validator = field_validator("zone")(hostname)


class Certificate(Strict):
    domains: list[str] = []
    mode: Literal["custom", "http", "dns"] = "custom"
    dns_profile_id: str | None = None
    email: str = ""
    terms_agreed: bool = False
    server: str = "https://acme-v02.api.letsencrypt.org/directory"
    profile: str | None = None
    key_type: Literal["ecdsa", "rsa"] = "ecdsa"
    reuse_key: bool = False
    must_staple: bool = False
    status: Literal["pending", "ready", "error"] = "pending"
    fingerprint: str | None = None
    expires_at: int | None = None

    @field_validator("domains")
    @classmethod
    def names_valid(cls, values):
        return [hostname(v) for v in values]


class AuthProvider(Strict):
    provider: Literal["authelia", "authentik", "oauth2proxy", "tinyauth", "voidauth", "anubis"]
    url: str
    signin_url: str
    redirect_login: bool = True
    identity_headers: list[
        Literal[
            "Remote-User",
            "Remote-Email",
            "Remote-Groups",
            "X-Auth-Request-User",
            "X-Auth-Request-Email",
            "X-Authentik-Username",
            "X-Authentik-Email",
            "X-Authentik-Groups",
        ]
    ] = ["Remote-User", "Remote-Email", "Remote-Groups"]

    @field_validator("url", "signin_url")
    @classmethod
    def safe_url(cls, value):
        if not re.fullmatch(r"https?://[^\s\"'{};$\\]+", value):
            raise ValueError("Invalid provider URL")
        return value.rstrip("/")


class ClientCA(Strict):
    verify: Literal["on", "optional"] = "on"
    depth: int = Field(default=2, ge=1, le=10)
    fingerprint: str | None = None


class GeoPolicy(Strict):
    countries: list[str] = []
    asns: list[int] = []
    database_version: str = ""
    mode: Literal["allow", "deny"] = "deny"
    allow_private: bool = True
    allow_unknown: bool = True

    @field_validator("countries")
    @classmethod
    def country_codes(cls, values):
        if any(not re.fullmatch(r"[A-Z]{2}", v) for v in values):
            raise ValueError("ISO country codes required")
        return values

    @field_validator("asns")
    @classmethod
    def asn_numbers(cls, values):
        if any(not 1 <= value <= 4294967295 for value in values):
            raise ValueError("Invalid autonomous system number")
        return values


class CrowdSecProfile(Strict):
    lapi_url: str = "http://127.0.0.1:8080"
    appsec_url: str = "http://127.0.0.1:7422"
    appsec: bool = True
    observe: bool = False
    failure_action: Literal["deny", "allow"] = "deny"
    captcha_provider: Literal["off", "recaptcha", "hcaptcha", "turnstile"] = "off"

    @field_validator("lapi_url", "appsec_url")
    @classmethod
    def safe_url(cls, value):
        if not re.fullmatch(r"https?://[A-Za-z0-9_.:\[\]-]+", value):
            raise ValueError("Expected HTTP origin")
        return value


class Site(Strict):
    domains: list[str] = Field(min_length=1)
    root_id: str
    certificate_id: str | None = None
    php_upstream: str | None = None
    directory_index: bool = False
    fancyindex: bool = False

    @field_validator("domains")
    @classmethod
    def names_valid(cls, values):
        return [hostname(v) for v in values]

    @field_validator("root_id")
    @classmethod
    def root_valid(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
            raise ValueError("Invalid site root")
        return value


class Runtime(Strict):
    worker_connections: int = Field(default=1024, ge=128, le=1000000)
    ipv6: bool = True
    access_logs: bool = False
    analytics: bool = False
    mask_log_ips: bool = True
    log_retention_days: int = Field(default=7, ge=1, le=365)
    trusted_proxies: list[str] = []
    trust_cloudflare: bool = False
    proxy_protocol_http: bool = False
    proxy_protocol_https: bool = False
    mptcp: bool = False
    quic_bpf: bool = False
    default_response: Literal["404", "444", "html", "redirect"] = "404"
    default_html: str = ""
    default_redirect: str = "https://example.com"
    http_snippet: str = ""
    stream_snippet: str = ""

    @field_validator("trusted_proxies")
    @classmethod
    def cidrs(cls, values):
        return [str(ipaddress.ip_network(v, strict=False)) for v in values]


class ECH(Strict):
    public_name: str
    domains: list[str]
    dns_profile_id: str | None = None
    status: Literal["pending", "awaiting_dns", "ready"] = "pending"
    config: str = ""
    current_key: str = ""
    previous_key: str = ""
    pending_key: str = ""
    host_validator = field_validator("public_name")(hostname)


SCHEMAS = {
    "proxy-hosts": Route,
    "redirect-hosts": Redirect,
    "streams": Stream,
    "upstreams": Upstream,
    "access-lists": Access,
    "header-policies": Headers,
    "tls-policies": TLS,
    "dns-profiles": DNSProfile,
    "certificates": Certificate,
    "auth-providers": AuthProvider,
    "client-cas": ClientCA,
    "geo-policies": GeoPolicy,
    "crowdsec-profiles": CrowdSecProfile,
    "sites": Site,
    "runtime": Runtime,
    "ech": ECH,
}
ADMIN_KINDS = set(SCHEMAS) - {"proxy-hosts", "redirect-hosts", "streams", "access-lists", "upstreams"}


class ResourceInput(Strict):
    name: str = Field(min_length=1, max_length=128)
    data: dict
    enabled: bool = True
    credentials: dict[str, str] | None = None


class LoginInput(Strict):
    email: str
    password: str


class SetupInput(LoginInput):
    token: str
    language: Literal["ru", "en"] = "ru"


class UserInput(LoginInput):
    role: Literal["admin", "operator", "observer"] = "observer"
    language: Literal["ru", "en"] = "ru"
