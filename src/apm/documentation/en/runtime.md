# Server settings

Server-wide Angie settings; one resource is allowed. Changes require an apply. In existing mode APM manages its own includes while process-level settings remain in the Angie owner configuration. Administrator-only.

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

### `worker_connections`

<!-- setting:worker_connections -->
Maximum connections per Angie worker, including clients and upstreams. Account for OS file limits. In existing mode configure this in the main Angie configuration.

Format: `integer`. Default: `1024`. Constraints: minimum=128; maximum=1000000.

Example: `1024`.

### `ipv6`

<!-- setting:ipv6 -->
Add IPv6 HTTP/HTTPS/QUIC listeners to managed servers. The host needs IPv6 support; this does not create DNS AAAA records.

Format: `boolean`. Default: `true`.

Example: `true`.

### `access_logs`

<!-- setting:access_logs -->
Enable HTTP access logging and viewing in the panel. Off by default. URIs are logged without query parameters.

Format: `boolean`. Default: `false`.

Example: `false`.

### `analytics`

<!-- setting:analytics -->
Additional GoAccess-format log when access_logs is enabled. The report needs the analytics sidecar from compose.analytics.yaml.

Format: `boolean`. Default: `false`.

Example: `false`.

### `mask_log_ips`

<!-- setting:mask_log_ips -->
Mask IPs in HTTP logs: IPv4 to /24, IPv6 to leading groups; on by default. Affects diagnostics and analytics.

Format: `boolean`. Default: `true`.

Example: `true`.

### `log_retention_days`

<!-- setting:log_retention_days -->
Declared log retention setting. Current rotation uses APM_METRICS_RETENTION_DAYS; changing this field alone does not change cleanup retention.

Format: `integer`. Default: `7`. Constraints: minimum=1; maximum=365.

Example: `7`.

### `trusted_proxies`

<!-- setting:trusted_proxies -->
Trusted proxy IPs/CIDRs for X-Forwarded-For. Avoid untrusted networks: this affects ACLs, geography, limits and logged IPs.

Format: `array`. Default: `[]`.

Example: `["10.0.0.0/8"]`.

### `trust_cloudflare`

<!-- setting:trust_cloudflare -->
Trust current Cloudflare ranges. Refresh addresses with cloudflare.refresh first; applying fails if no list is cached.

Format: `boolean`. Default: `false`.

Example: `false`.

### `proxy_protocol_http`

<!-- setting:proxy_protocol_http -->
Expect PROXY protocol on the HTTP listener. Enable only behind a load balancer that sends this header.

Format: `boolean`. Default: `false`.

Example: `false`.

### `proxy_protocol_https`

<!-- setting:proxy_protocol_https -->
Expect PROXY protocol on the HTTPS listener. Incompatible with QUIC/HTTP3 in the current compiler.

Format: `boolean`. Default: `false`.

Example: `false`.

### `mptcp`

<!-- setting:mptcp -->
Enable Multipath TCP for TCP listeners. Requires OS and Angie support; the switch does not install it.

Format: `boolean`. Default: `false`.

Example: `false`.

### `quic_bpf`

<!-- setting:quic_bpf -->
Enable BPF-based QUIC routing. Requires Angie/OS capabilities; in existing mode configure it in the main configuration.

Format: `boolean`. Default: `false`.

Example: `false`.

### `default_response`

<!-- setting:default_response -->
Unknown HTTP host response: 404, close with 444, custom html or redirect. In existing mode the default server remains managed by the Angie owner.

Format: `string`. Default: `"404"`. Constraints: 404 / 444 / html / redirect.

Example: `"404"`.

### `default_html`

<!-- setting:default_html -->
HTML for default_response=html, stored as default.html within the revision and served only for unknown hosts.

Format: `string`. Default: `""`.

Example: `""`.

### `default_redirect`

<!-- setting:default_redirect -->
HTTP(S) redirect URL for default_response=redirect, such as https://example.com.

Format: `string`. Default: `"https://example.com"`.

Example: `"https://example.com"`.

### `http_snippet`

<!-- setting:http_snippet -->
Administrator directives in the http context. Do not paste a complete configuration; angie -t validates the candidate before activation.

Format: `string`. Default: `""`.

Example: `""`.

### `stream_snippet`

<!-- setting:stream_snippet -->
Administrator directives in the stream context. Changes go through validation, reload and generation confirmation.

Format: `string`. Default: `""`.

Example: `""`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
