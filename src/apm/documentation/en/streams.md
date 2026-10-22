# TCP / UDP

TCP/UDP forwarding without HTTP. Choose a free listening port and backend or group, then optional TLS/PROXY settings. Control-plane ports are reserved. Administrators and operators can edit streams.

## Settings

### `name`

<!-- setting:name -->
A label for finding and selecting this resource, e.g. test. It does not change its ID or linked resources.

Format: `string`. Default: `required`. Constraints: minLength=1; maxLength=128.

Example: `"test"`.

### `enabled`

<!-- setting:enabled -->
Include this resource in the generated configuration. Disabling keeps its settings in the panel. The change takes effect after saving and a successful apply.

Format: `boolean`. Default: `true`.

Example: `true`.

### `listen_port`

<!-- setting:listen_port -->
Incoming TCP/UDP port on Angie. Ports 80, 81, 443, 8181 and 18081 are reserved; the backend port is configured separately.

Format: `integer`. Default: `required`. Constraints: minimum=1; maximum=65535.

Example: `9000`.

### `protocol`

<!-- setting:protocol -->
tcp forwards a byte stream; udp forwards datagrams. UDP cannot use TCP TLS or incoming PROXY protocol here.

Format: `string`. Default: `"tcp"`. Constraints: tcp / udp.

Example: `"tcp"`.

### `host`

<!-- setting:host -->
Application IP address or host name. In Docker, use a service name reachable from Angie's network. For an application on macOS with Docker Desktop, use host.docker.internal. 127.0.0.1 refers to Angie's own environment.

Format: `string`. Default: `required`.

Example: `"127.0.0.1"`.

### `port`

<!-- setting:port -->
The application's listening port. For a Docker service in the same network, use its internal container port, for example 8080. This does not change the public port of the proxy host.

Format: `integer`. Default: `required`. Constraints: minimum=1; maximum=65535.

Example: `8080`.

### `upstream_id`

<!-- setting:upstream_id -->
Use a previously created group of application servers for balancing and failover. When selected, the group is used instead of this route's backend host and port.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `certificate_id`

<!-- setting:certificate_id -->
Ready certificate for incoming TCP TLS. Applying fails if ready material is unavailable. UDP cannot use this option.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `upstream_tls`

<!-- setting:upstream_tls -->
Enable TLS from Angie to the TCP application. Separate from the incoming certificate; combine with upstream_verify and upstream_sni.

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

### `proxy_protocol_in`

<!-- setting:proxy_protocol_in -->
Expect a PROXY protocol header before TCP data. Clients without it cannot connect; use behind a compatible load balancer only.

Format: `boolean`. Default: `false`.

Example: `false`.

### `proxy_protocol_out`

<!-- setting:proxy_protocol_out -->
Send PROXY protocol to the application to convey the original client address. The application must support this format.

Format: `boolean`. Default: `false`.

Example: `false`.

### `timeout_seconds`

<!-- setting:timeout_seconds -->
Stream proxy timeout in seconds, default 600. Applies to TCP/UDP connections rather than HTTP requests.

Format: `integer`. Default: `600`. Constraints: minimum=1; maximum=86400.

Example: `600`.

### `advanced`

<!-- setting:advanced -->
Administrator-owned Angie directives inside this host's server block. Do not paste a complete configuration or repeat generated blocks. The candidate is checked with angie -t; a rejected candidate keeps the previous working configuration.

Format: `string`. Default: `""`.

Example: `""`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
