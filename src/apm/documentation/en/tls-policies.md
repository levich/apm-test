# TLS policies

Shared incoming TLS settings. Create a policy and optional ECH configuration, then select it on an SSL host. Does not configure backend TLS verification. Some features depend on the Angie build; administrator-managed.

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

### `protocols`

<!-- setting:protocols -->
Allowed incoming TLS versions. The list cannot be empty. Usually use TLSv1.2 and TLSv1.3.

Format: `array`. Default: `["TLSv1.2", "TLSv1.3"]`. Constraints: TLSv1.2 / TLSv1.3.

Example: `["TLSv1.2", "TLSv1.3"]`.

### `ciphers`

<!-- setting:ciphers -->
OpenSSL cipher expression for ssl_ciphers, such as HIGH:!aNULL:!MD5:!3DES. This does not configure TLS 1.3 cipher suites.

Format: `string`. Default: `"HIGH:!aNULL:!MD5:!3DES"`.

Example: `"HIGH:!aNULL:!MD5:!3DES"`.

### `curves`

<!-- setting:curves -->
Key-exchange groups for ssl_ecdh_curve; auto delegates to the TLS library. angie -t validates support.

Format: `string`. Default: `"auto"`.

Example: `"auto"`.

### `ocsp`

<!-- setting:ocsp -->
Enable OCSP stapling and stapling verification for the selected certificate. Requires a compatible CA, chain and network access to its responder.

Format: `boolean`. Default: `false`.

Example: `false`.

### `certificate_compression`

<!-- setting:certificate_compression -->
TLS certificate compression. Requires Angie support; unrelated to compressing HTTP responses.

Format: `boolean`. Default: `false`.

Example: `false`.

### `ech_id`

<!-- setting:ech_id -->
Select a ready ECH configuration. The key activates after DNS confirmation; compatible Angie and TLS library are required.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
