# Client certificates

Client CAs for mutual TLS. Create a profile, upload CA PEM and optional CRL, then select it on an SSL host. Requires a real CA; invalid signatures or expired CRLs are rejected. Administrator-only.

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

### `verify`

<!-- setting:verify -->
For client CAs: on requires a client certificate, optional verifies one when supplied. This authenticates clients rather than the server certificate.

Format: `string`. Default: `"on"`. Constraints: on / optional.

Example: `"on"`.

### `depth`

<!-- setting:depth -->
Maximum client certificate chain depth. Match your PKI; too small a value rejects otherwise valid longer chains.

Format: `integer`. Default: `2`. Constraints: minimum=1; maximum=10.

Example: `2`.

### `fingerprint`

<!-- setting:fingerprint -->
System SHA-256 identifier for a PEM version. Read-only; paths are versioned and old revisions remain available for rollback.

Format: `string / null`. Default: `null`.

Example: `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
