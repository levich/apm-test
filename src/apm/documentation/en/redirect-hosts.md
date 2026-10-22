# Redirects

Browser redirects to another URL. Enter domains, destination and status, then an optional certificate. Conflicting route domains are rejected. Administrators and operators can create and edit redirects.

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

### `domains`

<!-- setting:domains -->
Host names without a protocol, port or path, one per line. For example: app.example.com. DNS records are configured separately. A wildcard certificate such as *.example.com requires DNS-01 validation.

Format: `array`. Default: `required`. Constraints: minItems=1.

Example: `["app.example.com"]`.

### `target`

<!-- setting:target -->
A complete HTTP(S) destination such as https://example.com. This redirects the browser rather than proxying the request.

Format: `string`. Default: `required`.

Example: `"https://example.com"`.

### `code`

<!-- setting:code -->
HTTP redirect status: 301/308 are permanent, 302/307 temporary; 307/308 preserve the request method.

Format: `integer`. Default: `301`. Constraints: 301 / 302 / 307 / 308.

Example: `301`.

### `preserve_uri`

<!-- setting:preserve_uri -->
Append the original URI and query to the destination. Disable to always redirect to one fixed URL.

Format: `boolean`. Default: `true`.

Example: `true`.

### `certificate_id`

<!-- setting:certificate_id -->
Incoming HTTPS certificate covering all redirect domains. Without it the listener remains HTTP; the destination certificate is configured on its own server.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
