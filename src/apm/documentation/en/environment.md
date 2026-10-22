# System settings

Settings are read from APM_* and .env at process startup. Restart affected services after changes, then apply configuration. Encode lists as JSON arrays. Values below are built-in defaults, not the contents of your .env.

## `APM_DATA_DIR`

<!-- environment:APM_DATA_DIR -->
Shared directory for SQLite, keys, certificates, revisions, logs and sites. Existing mode requires the same absolute path in every service.

Default: `"data"`.

Format: `string`. Example: `"data"`.

## `APM_DATABASE_URL`

<!-- environment:APM_DATABASE_URL -->
Database URL. Implementation and migrations target SQLite; other SQLAlchemy backends are not qualified without separate validation.

Default: `null`.

Format: `string / null`. Example: `"sqlite:////data/apm.sqlite3"`.

## `APM_COOKIE_SECURE`

<!-- environment:APM_COOKIE_SECURE -->
Send cookies over HTTPS only. false is intended for isolated local HTTP development.

Default: `true`.

Format: `boolean`. Example: `true`.

## `APM_SESSION_SECONDS`

<!-- environment:APM_SESSION_SECONDS -->
Server session lifetime in seconds, default 12 hours.

Default: `43200`.

Format: `integer`. Example: `43200`.

## `APM_AGENT_SOCKET`

<!-- environment:APM_AGENT_SOCKET -->
Agent Unix socket path. null uses APM_DATA_DIR/run/agent.sock. File permissions must allow the required service access.

Default: `null`.

Format: `string / null`. Example: `"/data/run/agent.sock"`.

## `APM_ANGIE_BINARY`

<!-- environment:APM_ANGIE_BINARY -->
Angie executable available to the agent; usually /usr/sbin/angie in existing mode.

Default: `"angie"`.

Format: `string`. Example: `"angie"`.

## `APM_ANGIE_MODE`

<!-- environment:APM_ANGIE_MODE -->
managed generates the full configuration; existing attaches http.conf/stream.conf to an existing server without replacing its root configuration.

Default: `"managed"`.

Format: `string`. Allowed values: managed, existing. Example: `"managed"`.

## `APM_ANGIE_CONFIG`

<!-- environment:APM_ANGIE_CONFIG -->
Root Angie configuration; null in managed uses APM_DATA_DIR/angie.conf. Existing mode requires an absolute existing path.

Default: `null`.

Format: `string / null`. Example: `"/etc/angie/angie.conf"`.

## `APM_ANGIE_PREFIX`

<!-- environment:APM_ANGIE_PREFIX -->
Prefix passed to Angie -p, shared by validation and reload. An absolute path is required in existing mode.

Default: `null`.

Format: `string / null`. Example: `"/etc/angie"`.

## `APM_ANGIE_STATUS_URL`

<!-- environment:APM_ANGIE_STATUS_URL -->
Local Angie API exposing generation for reload confirmation. Must be reachable by the agent and kept private.

Default: `"http://127.0.0.1:18081/status/angie"`.

Format: `string`. Example: `"http://127.0.0.1:18081/status/angie"`.

## `APM_BACKEND_URL`

<!-- environment:APM_BACKEND_URL -->
Manager address used by Angie to proxy the panel. Local Compose uses http://manager:8181. Worker and agent values must match.

Default: `"http://127.0.0.1:8181"`.

Format: `string`. Example: `"http://127.0.0.1:8181"`.

## `APM_ADMIN_LISTEN`

<!-- environment:APM_ADMIN_LISTEN -->
HTTPS panel address and port in the managed Angie configuration, such as 0.0.0.0:81. Does not change the manager process port.

Default: `"0.0.0.0:81"`.

Format: `string`. Example: `"0.0.0.0:81"`.

## `APM_DEFAULT_LANGUAGE`

<!-- environment:APM_DEFAULT_LANGUAGE -->
Default language: ru or en. User language and the UI language cookie determine the displayed language thereafter.

Default: `"ru"`.

Format: `string`. Example: `"ru"`.

## `APM_DOCKER_URL`

<!-- environment:APM_DOCKER_URL -->
Read-only Docker gateway origin for discovery, such as http://docker-gateway:2375. Do not expose an unprotected Docker API publicly.

Default: `"http://docker-gateway:2375"`.

Format: `string`. Example: `"http://docker-gateway:2375"`.

## `APM_DISCOVERY_ENABLED`

<!-- environment:APM_DISCOVERY_ENABLED -->
Start Docker events and periodic label reconciliation. Explicit network and domain allowlists are also required.

Default: `false`.

Format: `boolean`. Example: `false`.

## `APM_DISCOVERY_NETWORKS`

<!-- environment:APM_DISCOVERY_NETWORKS -->
JSON array of permitted Docker networks, e.g. ["apps"]. The container needs IPv4 in the selected network.

Default: `[]`.

Format: `array`. Example: `["apps"]`.

## `APM_DISCOVERY_DOMAINS`

<!-- environment:APM_DISCOVERY_DOMAINS -->
JSON array of permitted domain zones, e.g. ["example.com"]. Discovery does not import domains outside the list.

Default: `[]`.

Format: `array`. Example: `["example.com"]`.

## `APM_DISCOVERY_ACME_TERMS_AGREED`

<!-- environment:APM_DISCOVERY_ACME_TERMS_AGREED -->
Explicit ACME terms agreement for automatic Docker discovery certificate requests.

Default: `false`.

Format: `boolean`. Example: `false`.

## `APM_ACME_EMAIL`

<!-- environment:APM_ACME_EMAIL -->
ACME account email for automatically created certificates. Use the system owner’s address.

Default: `""`.

Format: `string`. Example: `"admin@example.com"`.

## `APM_OIDC_ISSUER`

<!-- environment:APM_OIDC_ISSUER -->
OpenID Connect issuer; empty disables OIDC. Metadata comes from /.well-known/openid-configuration.

Default: `""`.

Format: `string`. Example: `"https://id.example.com"`.

## `APM_OIDC_CLIENT_ID`

<!-- environment:APM_OIDC_CLIENT_ID -->
APM application client ID at the OIDC provider. Used with issuer and an optional client secret.

Default: `""`.

Format: `string`. Example: `"apm"`.

## `APM_OIDC_CLIENT_SECRET_FILE`

<!-- environment:APM_OIDC_CLIENT_SECRET_FILE -->
OIDC client secret file read at manager startup. The secret is not entered on the user form.

Default: `null`.

Format: `string / null`. Example: `"/run/secrets/oidc-client-secret"`.

## `APM_PUBLIC_URL`

<!-- environment:APM_PUBLIC_URL -->
Public panel URL and OIDC callback base. Does not automatically create DNS, listeners or a certificate.

Default: `"https://localhost:81"`.

Format: `string`. Example: `"https://localhost:81"`.

## `APM_OIDC_ONLY`

<!-- environment:APM_OIDC_ONLY -->
Disable ordinary password login and use OIDC. Bind an existing administrator to an OIDC subject first.

Default: `false`.

Format: `boolean`. Example: `false`.

## `APM_CERTBOT_BINARY`

<!-- environment:APM_CERTBOT_BINARY -->
Certbot executable in the worker. Uses certonly; EAB secrets are passed through a temporary file.

Default: `"certbot"`.

Format: `string`. Example: `"certbot"`.

## `APM_ACME_SERVER`

<!-- environment:APM_ACME_SERVER -->
ACME directory URL for automatically created certificates. Individual certificate resources have their own server field.

Default: `"https://acme-v02.api.letsencrypt.org/directory"`.

Format: `string`. Example: `"https://acme-v02.api.letsencrypt.org/directory"`.

## `APM_METRICS_RETENTION_DAYS`

<!-- environment:APM_METRICS_RETENTION_DAYS -->
Metrics history and rotated log retention in days. History is additionally bounded to 10080 points.

Default: `7`.

Format: `integer`. Example: `7`.

## `APM_PRE_RUN_DIR`

<!-- environment:APM_PRE_RUN_DIR -->
Directory of deployment-owned *.sh hooks. Files must not be symlinks or group/world writable; each gets a 60-second timeout.

Default: `"/etc/apm/pre-run.d"`.

Format: `string`. Example: `"/etc/apm/pre-run.d"`.

## `APM_DEVELOPMENT`

<!-- environment:APM_DEVELOPMENT -->
Development mode. This does not replace configuring cookie_secure or limiting backend exposure.

Default: `false`.

Format: `boolean`. Example: `false`.

## `APM_ANGIE_IMAGE`

<!-- environment:APM_ANGIE_IMAGE -->
Compose/build input rather than a Python setting. Default docker.angie.software/angie:1.12.4-debian. Select an image with compatible required modules; PRO requires your own license.

[Compose](deployment.md) · [Docker discovery](discovery.md) · [Runtime](runtime.md)
