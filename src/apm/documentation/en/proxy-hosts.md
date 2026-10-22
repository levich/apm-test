# Proxy hosts

HTTP(S) and gRPC application routes. Prepare backends/upstreams and policies, enter domains, then SSL and locations. Saving queues an apply; confirm its outcome in Operations. Administrators and operators can manage routes; operators cannot change administrative policies.

## Settings

### `name`

<!-- setting:name -->
A name for finding this resource in the panel. For a proxy host, incoming requests are matched by Domain names, not this name.

Format: `string`. Default: `required`. Constraints: minLength=1; maxLength=128.

Example: `"test"`.

### `enabled`

<!-- setting:enabled -->
Include this resource in the generated configuration. Disabling keeps its settings in the panel. The change takes effect after saving and a successful apply.

Format: `boolean`. Default: `true`.

Example: `true`.

### `path`

<!-- setting:path -->
URL path handled by this location, for example / or /api/. The default / handles requests not matched by a more specific configured path. Use Custom locations to route parts of the site to other backends.

Format: `string`. Default: `"/"`.

Example: `"/"`.

### `host`

<!-- setting:host -->
Application IP address or host name. In Docker, use a service name reachable from Angie's network. For an application on macOS with Docker Desktop, use host.docker.internal. 127.0.0.1 refers to Angie's own environment.

Format: `string`. Default: `"127.0.0.1"`.

Example: `"127.0.0.1"`.

### `port`

<!-- setting:port -->
The application's listening port. For a Docker service in the same network, use its internal container port, for example 8080. This does not change the public port of the proxy host.

Format: `integer`. Default: `8080`. Constraints: minimum=1; maximum=65535.

Example: `8080`.

### `scheme`

<!-- setting:scheme -->
Protocol used between Angie and the application: HTTP, HTTPS, gRPC or gRPCS. Choose the protocol the application actually accepts. Browser-facing HTTPS is configured separately on the SSL tab.

Format: `string`. Default: `"http"`. Constraints: http / https / grpc / grpcs.

Example: `"http"`.

### `upstream_id`

<!-- setting:upstream_id -->
Use a previously created group of application servers for balancing and failover. When selected, the group is used instead of this route's backend host and port.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `access_ids`

<!-- setting:access_ids -->
Ordered IP and Basic Auth access lists. Use the arrows to change their order. The first list supplies the authentication combination and Authorization forwarding policy. An empty selection adds no access list at this level.

Format: `array`. Default: `[]`.

Example: `[]`.

### `access_mode`

<!-- setting:access_mode -->
inherit uses this path's lists or inherits the host's lists when none are selected. replace requires this path's own list. public removes IP/Basic Auth lists for this path; external authentication and other host protection still apply.

Format: `string`. Default: `"inherit"`. Constraints: inherit / replace / public.

Example: `"inherit"`.

### `auth_provider_id`

<!-- setting:auth_provider_id -->
Delegate access checks to a configured authentication service, such as Authelia or Authentik. A location without its own provider inherits the host's provider. The authentication service must be reachable from Angie.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `strip_prefix`

<!-- setting:strip_prefix -->
For HTTP/HTTPS backends, replace the matched path prefix with / before forwarding. For a location /api/, /api/users is sent as /users. Leave disabled if the application expects to receive /api/users.

Format: `boolean`. Default: `false`.

Example: `false`.

### `domains`

<!-- setting:domains -->
Host names without a protocol, port or path, one per line. For example: app.example.com. DNS records are configured separately. A wildcard certificate such as *.example.com requires DNS-01 validation.

Format: `array`. Default: `required`. Constraints: minItems=1.

Example: `["app.example.com"]`.

### `tls`

<!-- setting:tls -->
HTTP-01 proves domain ownership through public TCP port 80; DNS must point to the server. DNS-01 creates a TXT record through a DNS profile and supports wildcard names. DNS-01 does not require public port 80.

Format: `string`. Default: `"off"`. Constraints: off / http / dns / certificate.

Example: `"off"`.

### `certificate_id`

<!-- setting:certificate_id -->
Certificate for incoming TLS connections. In the proxy host editor, select an existing certificate or request a new one. It must cover every configured domain. A new request is queued on save; HTTPS requires successful issuance and apply.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `dns_profile_id`

<!-- setting:dns_profile_id -->
Previously created DNS account profile. DNS-01 needs permission to update TXT records in the domain's zone. Create and test the profile in DNS providers; its credentials are not entered in this host form.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `acme_email`

<!-- setting:acme_email -->
Email supplied to the certificate authority for the ACME account. Use an address you control. It is not a domain name, application login or DNS API credential.

Format: `string`. Default: `""`.

Example: `"admin@example.com"`.

### `acme_terms_agreed`

<!-- setting:acme_terms_agreed -->
Explicitly accept the selected certificate authority's terms before requesting a certificate. This checkbox is required for a new request. Opening help does not accept the terms or start issuance.

Format: `boolean`. Default: `false`.

Example: `false`.

### `force_ssl`

<!-- setting:force_ssl -->
Redirect application requests from HTTP to HTTPS when TLS is enabled. Enable only when clients can reach the HTTPS listener. The ACME HTTP-01 challenge path remains available for certificate validation.

Format: `boolean`. Default: `true`.

Example: `true`.

### `http2`

<!-- setting:http2 -->
Allow HTTP/2 on the incoming TLS listener. It can multiplex browser requests over one connection. This does not select the protocol between Angie and the backend.

Format: `boolean`. Default: `true`.

Example: `true`.

### `http3`

<!-- setting:http3 -->
Enable HTTP/3 over QUIC on the incoming HTTPS listener. Requires Angie support and reachable UDP on the HTTPS port, normally 443. TCP-only port forwarding is insufficient.

Format: `boolean`. Default: `false`.

Example: `false`.

### `locations`

<!-- setting:locations -->
Additional URL paths with their own application address and access settings. For example, route /api/ to an API service while the rest of the site uses the main backend. Duplicate paths are not allowed.

Format: `array`. Default: `[]`.

Example: `[{"path": "/api", "host": "127.0.0.1", "port": 8081}]`.

### `locations.path`

<!-- setting:locations.path -->
URL path handled by this location, for example / or /api/. The default / handles requests not matched by a more specific configured path. Use Custom locations to route parts of the site to other backends.

Format: `string`. Default: `"/"`.

Example: `"/"`.

### `locations.host`

<!-- setting:locations.host -->
Application IP address or host name. In Docker, use a service name reachable from Angie's network. For an application on macOS with Docker Desktop, use host.docker.internal. 127.0.0.1 refers to Angie's own environment.

Format: `string`. Default: `"127.0.0.1"`.

Example: `"127.0.0.1"`.

### `locations.port`

<!-- setting:locations.port -->
The application's listening port. For a Docker service in the same network, use its internal container port, for example 8080. This does not change the public port of the proxy host.

Format: `integer`. Default: `8080`. Constraints: minimum=1; maximum=65535.

Example: `8080`.

### `locations.scheme`

<!-- setting:locations.scheme -->
Protocol used between Angie and the application: HTTP, HTTPS, gRPC or gRPCS. Choose the protocol the application actually accepts. Browser-facing HTTPS is configured separately on the SSL tab.

Format: `string`. Default: `"http"`. Constraints: http / https / grpc / grpcs.

Example: `"http"`.

### `locations.upstream_id`

<!-- setting:locations.upstream_id -->
Use a previously created group of application servers for balancing and failover. When selected, the group is used instead of this route's backend host and port.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `locations.access_ids`

<!-- setting:locations.access_ids -->
Ordered IP and Basic Auth access lists. Use the arrows to change their order. The first list supplies the authentication combination and Authorization forwarding policy. An empty selection adds no access list at this level.

Format: `array`. Default: `[]`.

Example: `[]`.

### `locations.access_mode`

<!-- setting:locations.access_mode -->
inherit uses this path's lists or inherits the host's lists when none are selected. replace requires this path's own list. public removes IP/Basic Auth lists for this path; external authentication and other host protection still apply.

Format: `string`. Default: `"inherit"`. Constraints: inherit / replace / public.

Example: `"inherit"`.

### `locations.auth_provider_id`

<!-- setting:locations.auth_provider_id -->
Delegate access checks to a configured authentication service, such as Authelia or Authentik. A location without its own provider inherits the host's provider. The authentication service must be reachable from Angie.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `locations.strip_prefix`

<!-- setting:locations.strip_prefix -->
For HTTP/HTTPS backends, replace the matched path prefix with / before forwarding. For a location /api/, /api/users is sent as /users. Leave disabled if the application expects to receive /api/users.

Format: `boolean`. Default: `false`.

Example: `false`.

### `header_policy_id`

<!-- setting:header_policy_id -->
Reusable response and upstream header settings, including HSTS and framing rules. The policy can affect application behavior. Removing response headers may require an additional Angie module.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `tls_policy_id`

<!-- setting:tls_policy_id -->
Reusable policy for incoming TLS versions, ciphers and optional TLS features. Some options require additional capabilities. This is independent of verification of the backend's TLS certificate.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `client_ca_id`

<!-- setting:client_ca_id -->
Check client certificates against the selected CA for mutual TLS. The CA profile decides whether a certificate is required (on) or optional. This authenticates connecting clients and does not supply the server certificate.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `geo_policy_id`

<!-- setting:geo_policy_id -->
Restrict requests by configured country or ASN rules. Requires GeoIP support and downloaded databases. The selected policy also controls handling of private and unknown addresses.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `crowdsec_profile_id`

<!-- setting:crowdsec_profile_id -->
Apply the selected CrowdSec/AppSec profile. Requires compatible Lua modules, integration files and access to the security service. This build supports one shared CrowdSec profile per server.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `request_buffering`

<!-- setting:request_buffering -->
For HTTP/HTTPS backends, read the request body into Angie buffers before sending it to the application. Disabling can help streaming uploads. AppSec requires request buffering in this project.

Format: `boolean`. Default: `true`.

Example: `true`.

### `response_buffering`

<!-- setting:response_buffering -->
Buffer HTTP/HTTPS backend responses in Angie before delivery to the client. Disabling can help streaming and Server-Sent Events. It also means slow clients can keep backend connections busy longer.

Format: `boolean`. Default: `true`.

Example: `true`.

### `upstream_compression`

<!-- setting:upstream_compression -->
For HTTP/HTTPS backends, allow the client's Accept-Encoding header to reach the application. When disabled, Angie clears it. Response compression toward the client is controlled separately by Response compression.

Format: `boolean`. Default: `false`.

Example: `false`.

### `upstream_verify`

<!-- setting:upstream_verify -->
Verify the HTTPS/gRPCS backend certificate against the configured system CA bundle. Keep enabled for trusted TLS connections. Disabling removes certificate verification; it does not repair an invalid certificate.

Format: `boolean`. Default: `true`.

Example: `true`.

### `upstream_sni`

<!-- setting:upstream_sni -->
TLS server name used for backend SNI and certificate verification. Usually the DNS name on the application's certificate. When empty, Angie uses the configured backend host.

Format: `string / null`. Default: `null`.

Example: `"app.example.com"`.

### `compression`

<!-- setting:compression -->
Compress responses sent to the client. Gzip is available in the basic build; Brotli and Zstd require matching Angie modules. Compression uses server CPU and is usually unnecessary for already compressed files.

Format: `string`. Default: `"off"`. Constraints: off / gzip / brotli / zstd.

Example: `"off"`.

### `rate`

<!-- setting:rate -->
Request limit per client IP for this host, in requests per second. 0 disables it. The generated configuration allows a burst of 20 excess requests; further excess requests may be rejected.

Format: `integer`. Default: `0`. Constraints: minimum=0; maximum=100000.

Example: `0`.

### `connection_limit`

<!-- setting:connection_limit -->
Limit simultaneous connections per client IP for this host. 0 disables it. Clients sharing an address, such as users behind one NAT gateway, share the limit.

Format: `integer`. Default: `0`. Constraints: minimum=0; maximum=100000.

Example: `0`.

### `max_body_mb`

<!-- setting:max_body_mb -->
Maximum request body size in MB, including uploads. Default: 100. Requests above the limit receive HTTP 413. Increase it only when the application needs larger uploads.

Format: `integer`. Default: `100`. Constraints: minimum=1; maximum=100000.

Example: `100`.

### `timeout_seconds`

<!-- setting:timeout_seconds -->
HTTP/HTTPS backend read timeout in seconds, normally 60. Increase it for applications that pause longer between response data. It is not a guaranteed total request duration. This setting is not applied to gRPC/gRPCS in the current compiler.

Format: `integer`. Default: `60`. Constraints: minimum=1; maximum=86400.

Example: `60`.

### `noindex`

<!-- setting:noindex -->
Send X-Robots-Tag: noindex, nofollow to cooperating search engines. This is an indexing request, not access control: the host remains reachable unless you configure access protection.

Format: `boolean`. Default: `false`.

Example: `false`.

### `blocked_user_agents`

<!-- setting:blocked_user_agents -->
Block requests whose User-Agent contains a listed string, ignoring case. Enter one per line. User-Agent can be changed by the client, so this is not a substitute for authentication.

Format: `array`. Default: `[]`.

Example: `["ExampleBot"]`.

### `websocket`

<!-- setting:websocket -->
Forward the Upgrade and Connection headers required by WebSocket applications. Keep enabled for chats, live dashboards and other applications using WebSocket.

Format: `boolean`. Default: `true`.

Example: `true`.

### `advanced`

<!-- setting:advanced -->
Administrator-owned Angie directives inside this host's server block. Do not paste a complete configuration or repeat generated blocks. The candidate is checked with angie -t; a rejected candidate keeps the previous working configuration.

Format: `string`. Default: `""`.

Example: `""`.

## Availability and SSL

The agent checks from Angie’s network every 30 seconds, with up to 8 concurrent connections and a 3-second timeout. Results older than 90 seconds are stale. HTTP GET uses the configured path; strip_prefix replaces it with /. Checks use the first domain as Host, upstream_sni and upstream_verify. A 2xx–4xx response means available, 5xx means failure; redirects are not followed. gRPC checks TCP and gRPCS checks TLS. This checks connectivity, not the gRPC Health API. All paths and non-down members, including backups, are checked: mixed results mean partially available. Changed targets invalidate previous results.

The resource name opens the first non-wildcard domain; wildcard hosts need a concrete subdomain. SSL indicates the host setting; certificate validity inspects stored PEM/key, dates and SAN. It does not connect to the public domain or establish public CA trust. Saving and issuing do not confirm application; check Operations.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
