# Upstream groups

Server groups for balancing routes and streams. Add members, choose a strategy and select the group on a route. A group replaces the individual route address and port. Backend failures do not automatically roll back configuration.

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

### `peers`

<!-- setting:peers -->
Group members: at least one address and port. Each has a weight, backup and manually down flags. Availability checks include all members not marked down.

Format: `array`. Default: `required`. Constraints: minItems=1.

Example: `[{"host": "127.0.0.1", "port": 8080}]`.

### `peers.host`

<!-- setting:peers.host -->
Application IP address or host name. In Docker, use a service name reachable from Angie's network. For an application on macOS with Docker Desktop, use host.docker.internal. 127.0.0.1 refers to Angie's own environment.

Format: `string`. Default: `required`.

Example: `"127.0.0.1"`.

### `peers.port`

<!-- setting:peers.port -->
The application's listening port. For a Docker service in the same network, use its internal container port, for example 8080. This does not change the public port of the proxy host.

Format: `integer`. Default: `80`. Constraints: minimum=1; maximum=65535.

Example: `8080`.

### `peers.weight`

<!-- setting:peers.weight -->
Relative balancing weight. A value of 2 receives approximately twice the traffic of 1 when the selected strategy uses weights.

Format: `integer`. Default: `1`. Constraints: minimum=1; maximum=1000.

Example: `1`.

### `peers.backup`

<!-- setting:peers.backup -->
A backup used when primary servers are unavailable. Incompatible with ip_hash. Monitoring checks backup servers too.

Format: `boolean`. Default: `false`.

Example: `false`.

### `peers.down`

<!-- setting:peers.down -->
Manually exclude the member from balancing and checks. Its settings remain; clear this flag after recovery.

Format: `boolean`. Default: `false`.

Example: `false`.

### `strategy`

<!-- setting:strategy -->
round_robin rotates requests, least_conn selects fewer connections, ip_hash maps the client IP to a server. Stream ip_hash compiles to consistent hashing.

Format: `string`. Default: `"round_robin"`. Constraints: round_robin / least_conn / ip_hash.

Example: `"round_robin"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
