import hashlib
import ipaddress
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from apm.config import Settings


class CompileError(ValueError):
    pass


def q(value) -> str:
    text = str(value)
    if any(c in text for c in ("\x00", "\r", "\n")):
        raise CompileError("Control characters are forbidden in directive values")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def address(host, port):
    try:
        if ipaddress.ip_address(host).version == 6:
            host = f"[{host}]"
    except ValueError:
        pass
    return f"{host}:{port}"


def ident(value):
    return "apm_" + hashlib.sha256(value.encode()).hexdigest()[:20]


def filename_slug(value):
    alphabet = dict(zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh sch _ y _ e yu ya".split(),
    ))
    value = "".join(alphabet.get(c, c) for c in unicodedata.normalize("NFKC", value).casefold())
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9_-]+", "-", value).strip("-_")[:90] or "resource"


@dataclass
class Bundle:
    config: str
    files: dict[str, str] = field(default_factory=dict)


class Compiler:
    def __init__(self, config: Settings, capabilities: dict, root: Path, secret_resolver=None):
        self.settings = config
        self.caps = capabilities
        self.root = root
        self.files = {}
        self.secrets = secret_resolver or (lambda obj: {})
        self.resources = {}
        self.runtime = {}
        self.http_extras = []
        self.names = {}
        self.http_policy = []

    def fragment(self, scope, obj, lines):
        kind = {
            "proxy-hosts": "proxy", "redirect-hosts": "redirect", "streams": "stream",
            "sites": "site", "upstreams": "upstream",
        }[obj["kind"]]
        name = f"{scope}/{self.names[obj['id']]}.{kind}.conf"
        if scope == "http" and self.settings.angie_mode == "existing":
            lines = [part for line in lines
                     for part in ([line, *self.http_policy] if line == "server {" else [line])]
        self.files[name] = "\n".join(lines) + "\n"
        return f"include {q(self.root / name)};"

    def need(self, feature):
        info = self.caps.get(feature, {})
        if info is not True and not (isinstance(info, dict) and info.get("supported")):
            raise CompileError(f"Unsupported capability: {feature}")

    def ref(self, object_id, kind):
        obj = self.resources.get(object_id)
        if not obj or obj["kind"] != kind:
            raise CompileError(f"Missing or disabled {kind}: {object_id}")
        return obj

    def certificate(self, object_id):
        if not object_id:
            return None
        obj = self.ref(object_id, "certificates")
        data = obj["data"]
        fingerprint = data.get("fingerprint")
        import time

        if (
            not fingerprint
            or data.get("status") not in ("ready", "error")
            or (data.get("expires_at") or 0) <= time.time()
        ):
            return None
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise CompileError("Invalid certificate fingerprint")
        directory = self.settings.data_dir / "certificates" / obj["id"] / fingerprint
        return directory

    def listeners(self, certificate=None, http2=True, http3=False):
        r = self.runtime
        ipv6 = r.get("ipv6", True)
        proxy_http = " proxy_protocol" if r.get("proxy_protocol_http") else ""
        proxy_https = " proxy_protocol" if r.get("proxy_protocol_https") else ""
        if r.get("mptcp"):
            self.need("mptcp")
            proxy_http += " multipath"
            proxy_https += " multipath"
        lines = [f"listen 80{proxy_http};"]
        if ipv6:
            lines.append(f"listen [::]:80{proxy_http};")
        if certificate:
            lines.append(f"listen 443 ssl{proxy_https};")
            if ipv6:
                lines.append(f"listen [::]:443 ssl{proxy_https};")
            if http2:
                lines.append("http2 on;")
            if http3:
                self.need("http3")
                if proxy_https:
                    raise CompileError("PROXY protocol HTTPS listener conflicts with QUIC")
                lines += ["listen 443 quic;", "add_header Alt-Svc 'h3=\":443\"; ma=86400' always;"]
                if ipv6:
                    lines.append("listen [::]:443 quic;")
            lines += [
                f"ssl_certificate {q(certificate / 'fullchain.pem')};",
                f"ssl_certificate_key {q(certificate / 'privkey.pem')};",
            ]
        return lines

    def acl(self, ids, scope):
        if not ids:
            return []
        access = [self.ref(i, "access-lists") for i in ids]
        lines = [f"satisfy {access[0]['data']['satisfy']};"]
        passwords = {}
        rules = []
        for obj in access:
            rules.extend(obj["data"]["rules"])
            credentials = self.secrets(obj)
            for username in obj["data"].get("users", []):
                if not credentials.get(username):
                    raise CompileError("An access list has a Basic Auth user without a password")
                if username in passwords and passwords[username] != credentials[username]:
                    raise CompileError("Conflicting Basic Auth passwords across ordered access lists")
                passwords[username] = credentials[username]
        for rule in rules:
            lines.append(f"{rule['action']} {rule['address']};")
        if rules and not any(v["address"] == "all" for v in rules):
            lines.append("deny all;")
        if passwords:
            name = f"auth/{ident(scope)}.htpasswd"
            for username, hashed in passwords.items():
                if (
                    not re.fullmatch(r"[A-Za-z0-9_.@-]+", username)
                    or "\n" in hashed
                    or not hashed.startswith(("$6$", "$apr1$", "$2y$", "$2b$"))
                ):
                    raise CompileError("Invalid Basic Auth credentials")
            self.files[name] = "\n".join(f"{u}:{h}" for u, h in passwords.items()) + "\n"
            lines += ['auth_basic "Restricted";', f"auth_basic_user_file {q(self.root / name)};"]
        if not access[0]["data"].get("pass_auth", False):
            lines.append('proxy_set_header Authorization "";')
        return lines

    def tls(self, data):
        lines = []
        if policy_id := data.get("tls_policy_id"):
            policy = self.ref(policy_id, "tls-policies")["data"]
            lines += [
                f"ssl_protocols {' '.join(policy['protocols'])};",
                f"ssl_ciphers {q(policy['ciphers'])};",
                f"ssl_ecdh_curve {q(policy['curves'])};",
            ]
            if policy.get("ocsp"):
                lines += ["ssl_stapling on;", "ssl_stapling_verify on;"]
                cert = self.certificate(data.get("certificate_id"))
                if cert:
                    lines.append(f"ssl_trusted_certificate {q(cert / 'chain.pem')};")
            if policy.get("certificate_compression"):
                self.need("certificate_compression")
                lines.append("ssl_certificate_compression on;")
            if ech_id := policy.get("ech_id"):
                self.need("ech")
                ech = self.ref(ech_id, "ech")
                if not ech["data"].get("current_key"):
                    raise CompileError("ECH DNS activation is not confirmed")
                for field in ("current_key", "previous_key"):
                    key_id = ech["data"].get(field)
                    if key_id:
                        if not re.fullmatch(r"[a-f0-9]{32}", key_id):
                            raise CompileError("Invalid ECH key version")
                        directive = f"ssl_encrypted_hello_key {q(self.settings.data_dir / 'ech' / ech_id / (key_id + '.pem'))};"
                        if directive not in self.http_extras:
                            self.http_extras.append(directive)
        if ca_id := data.get("client_ca_id"):
            ca = self.ref(ca_id, "client-cas")
            if not re.fullmatch(r"[a-f0-9]{64}", ca["data"].get("fingerprint") or ""):
                raise CompileError("Upload client CA first")
            directory = self.settings.data_dir / "certificates" / ca_id / ca["data"]["fingerprint"]
            lines += [
                f"ssl_client_certificate {q(directory / 'ca.pem')};",
                f"ssl_verify_client {ca['data']['verify']};",
                f"ssl_verify_depth {ca['data']['depth']};",
            ]
            if (directory / "crl.pem").exists():
                lines.append(f"ssl_crl {q(directory / 'crl.pem')};")
        return lines

    def headers(self, data):
        lines = []
        if policy_id := data.get("header_policy_id"):
            policy = self.ref(policy_id, "header-policies")["data"]
            for name, value in policy["response"].items():
                lines.append(f"add_header {name} {q(value)} always;")
            for name, value in policy["upstream"].items():
                lines.append(f"proxy_set_header {name} {q(value)};")
            for name in policy["remove"]:
                self.need("headers_more")
                lines.append(f"more_clear_headers {q(name)};")
            if policy["hsts"]:
                value = "max-age=31536000" + ("; includeSubDomains" if policy["hsts_subdomains"] else "")
                lines.append(f"add_header Strict-Transport-Security {q(value)} always;")
            if policy["frame_options"] != "upstream":
                lines.append("proxy_hide_header X-Frame-Options;")
                if policy["frame_options"] != "remove":
                    lines.append(f"add_header X-Frame-Options {policy['frame_options']} always;")
        if data.get("noindex"):
            lines.append('add_header X-Robots-Tag "noindex, nofollow" always;')
        for agent in data.get("blocked_user_agents", []):
            expression = re.escape(agent).replace("\\ ", " ")
            lines.append(f"if ($http_user_agent ~* {q(expression)}) {{ return 403; }}")
        return lines

    def auth_location(self, provider_id, key):
        profile = self.ref(provider_id, "auth-providers")["data"]
        suffix = {
            "authelia": "/api/authz/auth-request",
            "authentik": "/outpost.goauthentik.io/auth/nginx",
            "oauth2proxy": "/oauth2/auth",
            "tinyauth": "/api/auth/nginx",
            "voidauth": "/api/authz/forward-auth",
            "anubis": "/.within.website/x/cmd/anubis/api/pass-challenge",
        }
        endpoint = profile["url"] + suffix[profile["provider"]]
        return [
            f"location = /_apm_auth_{key} {{",
            "internal;",
            f"proxy_pass {q(endpoint)};",
            "proxy_pass_request_body off;",
            'proxy_set_header Content-Length "";',
            "proxy_set_header X-Original-URL $scheme://$http_host$request_uri;",
            "proxy_set_header X-Original-Method $request_method;",
            "proxy_set_header X-Forwarded-For $remote_addr;",
            "proxy_set_header X-Forwarded-Proto $scheme;",
            "proxy_set_header X-Forwarded-Host $http_host;",
            "proxy_set_header X-Forwarded-Uri $request_uri;",
            "}",
        ]

    def location(self, data, parent, key):
        lines = [f"location {data['path']} {{"]
        if parent.get("tls") != "off" and parent.get("force_ssl"):
            lines.append("if ($scheme = http) { return 308 https://$host$request_uri; }")
        mode = data.get("access_mode", "inherit")
        effective_access = (
            []
            if mode == "public"
            else data.get("access_ids") or (parent.get("access_ids", []) if mode == "inherit" else [])
        )
        if mode == "replace" and not effective_access:
            raise CompileError(
                "Replacement access policy must have a list; select public explicitly for an exception"
            )
        lines += self.acl(effective_access, key)
        if parent.get("crowdsec_profile_id"):
            lines.append("access_by_lua_file /opt/apm/lua/access.lua;")
        auth_id = data.get("auth_provider_id") or parent.get("auth_provider_id")
        identity_headers = (
            "Remote-User",
            "Remote-Email",
            "Remote-Groups",
            "X-Auth-Request-User",
            "X-Auth-Request-Email",
            "X-Authentik-Username",
            "X-Authentik-Email",
            "X-Authentik-Groups",
            "X-Forwarded-User",
        )
        if auth_id:
            profile = self.ref(auth_id, "auth-providers")["data"]
            lines += [f"auth_request /_apm_auth_{key};"]
            for header in identity_headers:
                variable = "apm_identity_" + key + "_" + header.lower().replace("-", "_")
                if header in profile.get("identity_headers", ["Remote-User"]):
                    lines += [
                        f"auth_request_set ${variable} $upstream_http_{header.lower().replace('-', '_')};",
                        f"proxy_set_header {header} ${variable};",
                    ]
                else:
                    lines.append(f'proxy_set_header {header} "";')
            if profile.get("redirect_login", True):
                lines.append(f"error_page 401 = @apm_login_{key};")
        else:
            lines += [f'proxy_set_header {header} "";' for header in identity_headers]
        lines += [
            "proxy_set_header X-Real-IP $remote_addr;",
            "proxy_set_header X-Forwarded-For $remote_addr;",
            "proxy_set_header X-Forwarded-Proto $scheme;",
            "proxy_set_header Host $host;",
        ]
        scheme = data["scheme"]
        if data.get("upstream_id"):
            self.ref(data["upstream_id"], "upstreams")
            target = ident(data["upstream_id"])
        else:
            target = address(data["host"], data["port"])
        if scheme in ("grpc", "grpcs"):
            self.need("grpc")
            lines += [f"grpc_pass {q(scheme + '://' + target)};", "grpc_set_header Host $host;"]
            if scheme == "grpcs":
                lines += [
                    "grpc_ssl_server_name on;",
                    f"grpc_ssl_verify {'on' if parent.get('upstream_verify', True) else 'off'};",
                    "grpc_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;",
                    f"grpc_ssl_name {q(parent.get('upstream_sni') or data['host'])};",
                ]
        else:
            suffix = "/" if data.get("strip_prefix") else ""
            lines += [f"proxy_pass {q(scheme + '://' + target + suffix)};", "proxy_http_version 1.1;"]
            if parent.get("websocket", True):
                lines += [
                    "proxy_set_header Upgrade $http_upgrade;",
                    "proxy_set_header Connection $apm_connection;",
                ]
            lines += [
                f"proxy_request_buffering {'on' if parent.get('request_buffering', True) else 'off'};",
                f"proxy_buffering {'on' if parent.get('response_buffering', True) else 'off'};",
                f"proxy_read_timeout {parent.get('timeout_seconds', 60)}s;",
            ]
            if not parent.get("upstream_compression"):
                lines.append('proxy_set_header Accept-Encoding "";')
            if scheme == "https":
                lines += [
                    "proxy_ssl_server_name on;",
                    f"proxy_ssl_name {q(parent.get('upstream_sni') or data['host'])};",
                    f"proxy_ssl_verify {'on' if parent.get('upstream_verify', True) else 'off'};",
                    "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;",
                ]
        if parent.get("rate"):
            lines.append(f"limit_req zone={ident(parent['_id'])}_rate burst=20 nodelay;")
        if parent.get("connection_limit"):
            lines.append(f"limit_conn {ident(parent['_id'])}_conn {parent['connection_limit']};")
        lines += ["}"]
        if scheme in ("grpc", "grpcs"):
            lines = [line.replace("proxy_set_header ", "grpc_set_header ") for line in lines]
        if auth_id:
            lines += self.auth_location(auth_id, key)
            if profile.get("redirect_login", True):
                lines += [f"location @apm_login_{key} {{ return 302 {q(profile['signin_url'])}; }}"]
        return lines

    def proxy(self, obj):
        data = {**obj["data"], "_id": obj["id"]}
        key = ident(obj["id"])
        cert = self.certificate(data.get("certificate_id")) if data["tls"] != "off" else None
        lines = [
            "server {",
            *self.listeners(cert, data["http2"], data["http3"]),
            f"server_name {' '.join(data['domains'])};",
            f"status_zone {key};",
            f"client_max_body_size {data['max_body_mb']}m;",
            *self.headers(data),
        ]
        if cert:
            lines += self.tls(data)
        lines += [
            f"location ^~ /.well-known/acme-challenge/ {{ root {q(self.settings.data_dir / 'webroot')}; }}"
        ]
        if data["tls"] != "off" and not cert:
            lines += ["location / { return 503; }", "}"]
            return lines
        compression = data.get("compression", "off")
        if compression != "off":
            if compression != "gzip":
                self.need(compression)
            lines += [
                f"{compression} on;",
                f"{compression}_types text/plain text/css application/json application/javascript image/svg+xml;",
            ]
        if data["rate"]:
            self.http_extras.append(
                f"limit_req_zone $binary_remote_addr zone={key}_rate:1m rate={data['rate']}r/s;"
            )
        if data["connection_limit"]:
            self.http_extras.append(f"limit_conn_zone $binary_remote_addr zone={key}_conn:1m;")
        if geo_id := data.get("geo_policy_id"):
            self.need("geoip2")
            geo = self.ref(geo_id, "geo-policies")["data"]
            self.http_extras.append(
                f"map $apm_country ${key}_geo {{ default {'1' if geo['mode'] == 'deny' else '0'}; "
                + " ".join(
                    f"{country} {'0' if geo['mode'] == 'deny' else '1'};" for country in geo["countries"]
                )
                + (' "" 1;' if geo["allow_unknown"] else ' "" 0;')
                + " }"
            )
            condition = f"${key}_geo = 0"
            if geo.get("asns"):
                self.http_extras.append(
                    f"map $apm_asn ${key}_asn {{ default {'1' if geo['mode'] == 'deny' else '0'}; "
                    + " ".join(f"{asn} {'0' if geo['mode'] == 'deny' else '1'};" for asn in geo["asns"])
                    + " }"
                )
                if geo["mode"] == "deny":
                    self.http_extras.append(
                        f'map "${key}_geo:${key}_asn" ${key}_combined {{ default 0; "1:1" 1; }}'
                    )
                else:
                    self.http_extras.append(
                        f'map "${key}_geo:${key}_asn" ${key}_combined {{ default 1; "0:0" 0; }}'
                    )
                condition = f"${key}_combined = 0"
            if geo["allow_private"]:
                self.http_extras.append(
                    f'map "$apm_private:{condition.split()[0]}" ${key}_geo_final {{ default 1; "0:0" 0; }}'
                )
                condition = f"${key}_geo_final = 0"
            # Keep ACME challenge outside the access-phase geography rule.
            lines.append(f"set ${key}_geo_guard 1;")
            lines.append(f"if ({condition}) {{ set ${key}_geo_guard 0; }}")
        if data.get("crowdsec_profile_id"):
            self.need("crowdsec")
            profile = self.ref(data["crowdsec_profile_id"], "crowdsec-profiles")
            if profile["data"].get("appsec") and not data["request_buffering"]:
                raise CompileError("AppSec requires request buffering")
            lines += [f"set $apm_crowdsec_failure {q(profile['data']['failure_action'])};"]
        locations = [data, *data["locations"]]
        for index, location in enumerate(locations):
            if index and location["path"] == data["path"]:
                raise CompileError("Duplicate root location")
            loc_lines = self.location(location, data, f"{key}_{index}")
            if data.get("geo_policy_id"):
                loc_lines.insert(1, f"if (${key}_geo_guard = 0) {{ return 403; }}")
            lines += loc_lines
        if data.get("advanced"):
            lines += ["# Administrator snippet", data["advanced"]]
        return [*lines, "}"]

    def compile(self, resources: list[dict]):
        self.resources = {r["id"]: r for r in resources if r.get("enabled", True)}
        slugs = {obj["id"]: filename_slug(obj.get("name", obj["id"]))
                 for obj in self.resources.values()}
        counts = Counter((obj["kind"], slugs[obj["id"]]) for obj in self.resources.values())
        used = set()
        for obj in sorted(self.resources.values(), key=lambda value: value["id"]):
            slug = slugs[obj["id"]]
            if counts[obj["kind"], slug] > 1:
                slug += "-" + hashlib.sha256(obj["id"].encode()).hexdigest()[:12]
            while (obj["kind"], slug) in used:
                slug += "-" + hashlib.sha256(obj["id"].encode()).hexdigest()[:12]
            used.add((obj["kind"], slug))
            self.names[obj["id"]] = slug
        for obj in self.resources.values():
            if obj["kind"] == "runtime":
                self.runtime = obj["data"]
        root = self.settings.data_dir
        r = self.runtime
        existing = self.settings.angie_mode == "existing"
        http_policy = [
            "default_type application/octet-stream;",
            "server_tokens off;",
            "ssl_protocols TLSv1.2 TLSv1.3;",
            "ssl_session_tickets off;",
        ]
        http = [
            "map $http_upgrade $apm_connection { default upgrade; '' close; }",
            'log_format apm escape=json \'{"time":"$time_iso8601","ip":"$apm_log_ip","host":"$host",'
            '"method":"$request_method","path":"$uri","status":$status,"bytes":$body_bytes_sent,'
            '"duration":$request_time}\';',
        ]
        referenced_crowdsec = {
            obj["data"]["crowdsec_profile_id"]
            for obj in self.resources.values()
            if obj["kind"] == "proxy-hosts" and obj["data"].get("crowdsec_profile_id")
        }
        if len(referenced_crowdsec) > 1:
            raise CompileError("This bouncer build supports one shared CrowdSec profile per server")
        if referenced_crowdsec:
            self.need("crowdsec")
            profile = self.ref(next(iter(referenced_crowdsec)), "crowdsec-profiles")
            policy, secret = profile["data"], self.secrets(profile)
            if not secret.get("api_key"):
                raise CompileError("CrowdSec API key is required")
            values = {
                "ENABLED": "true",
                "MODE": "live",
                "API_URL": policy["lapi_url"],
                "API_KEY": secret["api_key"],
                "USE_TLS_AUTH": "false",
                "CACHE_EXPIRATION": "1",
                "BOUNCING_ON_TYPE": "all",
                "FALLBACK_REMEDIATION": "ban",
                "REQUEST_TIMEOUT": "3000",
                "UPDATE_FREQUENCY": "10",
                "ENABLE_INTERNAL": "false",
                "EXCLUDE_LOCATION": "",
                "BAN_TEMPLATE_PATH": "/opt/apm/src/apm/integrations/crowdsec/templates/ban.html",
                "REDIRECT_LOCATION": "",
                "RET_CODE": "403",
                "CAPTCHA_TEMPLATE_PATH": "/opt/apm/src/apm/integrations/crowdsec/templates/captcha.html",
                "CAPTCHA_EXPIRATION": "3600",
                "CAPTCHA_PROVIDER": ""
                if policy.get("captcha_provider", "off") == "off"
                else policy["captcha_provider"],
                "SITE_KEY": secret.get("site_key", ""),
                "SECRET_KEY": secret.get("secret_key", ""),
                "SSL_VERIFY": "true",
                "APPSEC_URL": policy["appsec_url"] if policy["appsec"] else "",
                "APPSEC_FAILURE_ACTION": "deny" if policy["failure_action"] == "deny" else "passthrough",
                "APPSEC_CONNECT_TIMEOUT": "1000",
                "APPSEC_SEND_TIMEOUT": "3000",
                "APPSEC_PROCESS_TIMEOUT": "3000",
                "ALWAYS_SEND_TO_APPSEC": "true",
                "APPSEC_DROP_UNREADABLE_BODY": "true",
            }
            if any("\n" in str(value) or "\r" in str(value) for value in values.values()):
                raise CompileError("Invalid bouncer setting")
            self.files["crowdsec.conf"] = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
            http += [
                "lua_package_path '/opt/apm/lua/?.lua;;';",
                "lua_shared_dict crowdsec_cache 50m;",
                "lua_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;",
                'init_by_lua_block { _G.apm_cs = require("apm").init('
                + q(self.root / "crowdsec.conf")
                + ", "
                + ("true" if policy.get("observe") else "false")
                + ", "
                + q(policy["failure_action"])
                + "); }",
            ]
        if r.get("mask_log_ips", True):
            http.insert(
                0,
                "map $remote_addr $apm_log_ip { ~^(?<apm_log_v4>[0-9]+\\.[0-9]+\\.[0-9]+)\\.[0-9]+$ $apm_log_v4.0; ~^(?<apm_log_v6>[0-9a-fA-F]+:[0-9a-fA-F]+:[0-9a-fA-F]+): $apm_log_v6::; default 0.0.0.0; }",
            )
        else:
            http.insert(0, "map $remote_addr $apm_log_ip { default $remote_addr; }")
        if r.get("access_logs"):
            http_policy.append(f"access_log {q(root / 'logs/access.log')} apm;")
            if r.get("analytics"):
                http.append(
                    'log_format apm_analytics \'$apm_log_ip - - [$time_local] "$request_method $uri $server_protocol" $status $body_bytes_sent "-" "$http_user_agent"\';'
                )
                http_policy.append(f"access_log {q(root / 'logs/analytics.log')} apm_analytics;")
        else:
            http_policy.append("access_log off;")
        for proxy in r.get("trusted_proxies", []):
            http_policy.append(f"set_real_ip_from {proxy};")
        if r.get("trust_cloudflare"):
            cidrs = self.caps.get("cloudflare_cidrs", [])
            if not cidrs:
                raise CompileError("Refresh Cloudflare IP ranges first")
            http_policy += [f"set_real_ip_from {ipaddress.ip_network(cidr)};" for cidr in cidrs]
        if r.get("trusted_proxies") or r.get("trust_cloudflare"):
            http_policy += ["real_ip_header X-Forwarded-For;", "real_ip_recursive on;"]
        if not existing:
            http = ["include /etc/angie/mime.types;", *http, *http_policy]
        if r.get("quic_bpf"):
            if existing:
                raise CompileError("Configure quic_bpf in the existing Angie main configuration")
            self.need("quic_bpf")
        if r.get("mptcp"):
            self.need("mptcp")
        managed_servers = [
            "server { listen 127.0.0.1:18081; location /status/ { api /status/; } }",
            f"server {{ listen {self.settings.admin_listen} ssl; server_name _;",
            f"ssl_certificate {q(root / 'bootstrap/fullchain.pem')};",
            f"ssl_certificate_key {q(root / 'bootstrap/privkey.pem')};",
            "add_header X-Content-Type-Options nosniff always;",
            f"location / {{ proxy_pass {q(self.settings.backend_url)}; proxy_set_header Host $http_host;",
            "proxy_set_header X-Forwarded-Proto https; proxy_buffering off; } }",
        ]
        default_return = r.get("default_response", "404")
        if default_return == "html":
            self.files["default.html"] = r.get("default_html", "")
            action = f"location / {{ root {q(self.root)}; try_files /default.html =404; }}"
        elif default_return == "redirect":
            from apm.schemas import Redirect

            url = Redirect.target_valid(r.get("default_redirect", "https://example.com"))
            action = f"location / {{ return 302 {q(url)}; }}"
        else:
            action = f"location / {{ return {int(default_return)}; }}"
        default_listens = [line[:-1] + " default_server;" for line in self.listeners(None, False, False)]
        managed_servers += [
            "server {",
            *default_listens,
            "server_name _;",
            f"location ^~ /.well-known/acme-challenge/ {{ root {q(root / 'webroot')}; }}",
            action,
            "}",
        ]
        if not existing:
            http += managed_servers
        self.http_policy = http_policy
        upstreams = [obj for obj in self.resources.values() if obj["kind"] == "upstreams"]
        https_hosts = [
            obj
            for obj in self.resources.values()
            if obj["kind"] in ("proxy-hosts", "redirect-hosts", "sites")
            and obj["data"].get("certificate_id")
            and (obj["kind"] != "proxy-hosts" or obj["data"].get("tls") != "off")
            and self.certificate(obj["data"]["certificate_id"])
        ]
        if https_hosts and not existing:
            default_tls = self.listeners(
                root / "bootstrap", False, any(obj["data"].get("http3") for obj in https_hosts)
            )
            default_tls = [
                line[:-1] + " default_server;"
                if line.startswith("listen 443") or line.startswith("listen [::]:443")
                else line
                for line in default_tls
                if not line.startswith("listen 80") and not line.startswith("listen [::]:80")
            ]
            default_tls = [
                line.replace(" quic", " quic reuseport") if " quic" in line else line for line in default_tls
            ]
            http += [
                "server {",
                *default_tls,
                "server_name _;",
                "ssl_reject_handshake on;",
                "return 404;",
                "}",
            ]
        for obj in upstreams:
            block = [f"upstream {ident(obj['id'])} {{", f"zone {ident(obj['id'])} 256k;"]
            if obj["data"]["strategy"] != "round_robin":
                block.append(obj["data"]["strategy"] + ";")
            for peer in obj["data"]["peers"]:
                flags = (
                    f"weight={peer['weight']}"
                    + (" backup" if peer["backup"] else "")
                    + (" down" if peer["down"] else "")
                )
                block.append(f"server {address(peer['host'], peer['port'])} {flags};")
            http.append(self.fragment("http", obj, [*block, "}"]))
        stream = [] if existing else ["access_log off;"]
        stream_upstreams = set()
        for obj in self.resources.values():
            data = obj["data"]
            http_start, stream_start = len(http), len(stream)
            if obj["kind"] == "proxy-hosts":
                http += self.proxy(obj)
            elif obj["kind"] == "redirect-hosts":
                cert = self.certificate(data.get("certificate_id"))
                destination = q(data["target"])
                if data["preserve_uri"]:
                    destination = destination[:-1] + '$request_uri"'
                http += [
                    "server {",
                    *self.listeners(cert),
                    f"server_name {' '.join(data['domains'])};",
                    f"location ^~ /.well-known/acme-challenge/ {{ root {q(root / 'webroot')}; }}",
                    f"location / {{ return {data['code']} {destination}; }}",
                    "}",
                ]
            elif obj["kind"] == "streams":
                target = address(data["host"], data["port"])
                if data.get("upstream_id"):
                    upstream = self.ref(data["upstream_id"], "upstreams")
                    name = ident(upstream["id"])
                    if upstream["id"] not in stream_upstreams:
                        upstream_start = len(stream)
                        stream += [f"upstream {name} {{", f"zone {name}_stream 256k;"]
                        strategy = upstream["data"]["strategy"]
                        if strategy == "least_conn":
                            stream.append("least_conn;")
                        elif strategy == "ip_hash":
                            stream.append("hash $remote_addr consistent;")
                        for peer in upstream["data"]["peers"]:
                            flags = (" backup" if peer["backup"] else "") + (" down" if peer["down"] else "")
                            stream.append(
                                f"server {address(peer['host'], peer['port'])} weight={peer['weight']}{flags};"
                            )
                        stream.append("}")
                        upstream_lines = stream[upstream_start:]
                        del stream[upstream_start:]
                        stream.append(self.fragment("stream", upstream, upstream_lines))
                        stream_upstreams.add(upstream["id"])
                        stream_start = len(stream)
                    target = name
                cert = self.certificate(data.get("certificate_id"))
                if data.get("certificate_id") and not cert:
                    raise CompileError("Stream certificate is not ready")
                flags = " udp reuseport" if data["protocol"] == "udp" else ""
                flags += " ssl" if cert else ""
                flags += " proxy_protocol" if data["proxy_protocol_in"] else ""
                if r.get("mptcp") and data["protocol"] == "tcp":
                    flags += " multipath"
                stream += [
                    "server {",
                    *(["access_log off;"] if existing else []),
                    f"listen {data['listen_port']}{flags};",
                    f"proxy_pass {q(target)};",
                    f"proxy_timeout {data['timeout_seconds']}s;",
                ]
                if cert:
                    stream += [
                        f"ssl_certificate {q(cert / 'fullchain.pem')};",
                        f"ssl_certificate_key {q(cert / 'privkey.pem')};",
                    ]
                if data["proxy_protocol_out"]:
                    stream.append("proxy_protocol on;")
                if data["upstream_tls"]:
                    stream += [
                        "proxy_ssl on;",
                        "proxy_ssl_server_name on;",
                        f"proxy_ssl_name {q(data.get('upstream_sni') or data['host'])};",
                        f"proxy_ssl_verify {'on' if data['upstream_verify'] else 'off'};",
                        "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;",
                    ]
                stream += [data.get("advanced", ""), "}"]
            elif obj["kind"] == "sites":
                cert = self.certificate(data.get("certificate_id"))
                if data.get("certificate_id") and not cert:
                    http += [
                        "server {",
                        *self.listeners(None),
                        f"server_name {' '.join(data['domains'])};",
                        "location / { return 503; }",
                        "}",
                    ]
                    lines = http[http_start:]
                    del http[http_start:]
                    http.append(self.fragment("http", obj, lines))
                    continue
                directory = root / "sites" / data["root_id"]
                http += [
                    "server {",
                    *self.listeners(cert),
                    f"server_name {' '.join(data['domains'])};",
                    f"root {q(directory)};",
                    "index index.html index.php;",
                    f"autoindex {'on' if data['directory_index'] else 'off'};",
                ]
                if data["fancyindex"]:
                    self.need("fancyindex")
                    http.append("fancyindex on;")
                if php := data.get("php_upstream"):
                    if not re.fullmatch(r"[A-Za-z0-9.:-]+", php):
                        raise CompileError("Invalid FPM address")
                    http += [
                        "location ~ \\.php$ { try_files $uri =404; include /etc/angie/fastcgi_params;",
                        "fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;",
                        f"fastcgi_pass {q(php)}; }}",
                    ]
                http += ["}"]
            if len(http) > http_start and obj["kind"] in ("proxy-hosts", "redirect-hosts", "sites"):
                lines = http[http_start:]
                del http[http_start:]
                http.append(self.fragment("http", obj, lines))
            if len(stream) > stream_start and obj["kind"] == "streams":
                lines = stream[stream_start:]
                del stream[stream_start:]
                stream.append(self.fragment("stream", obj, lines))
        geo_ids = {
            obj["data"]["geo_policy_id"]
            for obj in self.resources.values()
            if obj["kind"] == "proxy-hosts" and obj["data"].get("geo_policy_id")
        }
        if geo_ids:
            self.need("geoip2")
            versions = {
                self.ref(object_id, "geo-policies")["data"].get("database_version", "")
                for object_id in geo_ids
            }
            if len(versions) != 1 or not re.fullmatch(r"[a-f0-9]{64}", next(iter(versions))):
                raise CompileError("Update the GeoIP databases before using a geography policy")
            directory = root / "geoip" / next(iter(versions))
            http.insert(
                0, f"geoip2 {q(directory / 'GeoLite2-Country.mmdb')} {{ $apm_country country iso_code; }}"
            )
            http.insert(
                0, f"geoip2 {q(directory / 'GeoLite2-ASN.mmdb')} {{ $apm_asn autonomous_system_number; }}"
            )
            http.insert(
                0,
                "geo $apm_private { default 0; 127.0.0.0/8 1; 10.0.0.0/8 1; 172.16.0.0/12 1; 192.168.0.0/16 1; ::1 1; fc00::/7 1; }",
            )
        if existing:
            # Scope policies to APM virtual hosts; preserve the host's HTTP defaults.
            http = [
                part for line in http for part in ([line, *http_policy] if line == "server {" else [line])
            ]
        http = [*self.http_extras, *http, r.get("http_snippet", "")]
        stream.append(r.get("stream_snippet", ""))
        if existing:
            self.files["http.conf"] = "\n".join(http) + "\n"
            self.files["stream.conf"] = "\n".join(stream) + "\n"
            return Bundle("# Managed includes for an existing Angie instance.\n", self.files)
        modules = []
        for path in self.caps.get("module_paths", []):
            if not re.fullmatch(r"/[A-Za-z0-9_./-]+\.so", path):
                raise CompileError("Invalid module path from agent")
            modules.append(f"load_module {q(path)};")
        config = [
            *modules,
            "user angie apm;",
            "worker_processes auto;",
            f"pid {q(root / 'run/angie.pid')};",
            f"error_log {q(root / 'logs/error.log')} warn;",
            f"events {{ worker_connections {r.get('worker_connections', 1024)}; }}",
            "http {",
            *http,
            "}",
            "stream {",
            *stream,
            "}",
        ]
        if r.get("quic_bpf"):
            config.insert(0, "quic_bpf on;")
        return Bundle("\n".join(config) + "\n", self.files)


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
