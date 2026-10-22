# Response headers

Reusable HTTP header policies. Create a policy and attach it to a proxy host. Removing headers requires headers_more. Administrators manage policies; a missing module leaves the previous configuration active.

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

### `response`

<!-- setting:response -->
Response headers to the browser, one Header-Name=value per line. Example: Referrer-Policy=same-origin. Values are escaped by the compiler.

Format: `object`. Default: `{}`.

Example: `{"Referrer-Policy": "same-origin"}`.

### `upstream`

<!-- setting:upstream -->
Headers sent to the application, one Header-Name=value per line. Use trusted fixed values only.

Format: `object`. Default: `{}`.

Example: `{"X-Application": "example"}`.

### `remove`

<!-- setting:remove -->
Response header names to remove, one per line. Requires headers_more; applying fails when it is unavailable.

Format: `array`. Default: `[]`.

Example: `["X-Powered-By"]`.

### `hsts`

<!-- setting:hsts -->
Send Strict-Transport-Security with max-age=31536000. Enable after verifying HTTPS: browsers remember the TLS requirement.

Format: `boolean`. Default: `false`.

Example: `false`.

### `hsts_subdomains`

<!-- setting:hsts_subdomains -->
Add includeSubDomains to HSTS. Every subdomain must support HTTPS; effective when hsts is enabled.

Format: `boolean`. Default: `false`.

Example: `false`.

### `frame_options`

<!-- setting:frame_options -->
X-Frame-Options policy: upstream preserves the application response; DENY prevents framing, SAMEORIGIN permits the same origin, remove removes the header.

Format: `string`. Default: `"upstream"`. Constraints: upstream / DENY / SAMEORIGIN / remove.

Example: `"upstream"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
