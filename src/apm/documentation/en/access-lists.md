# Access lists

Ordered IP rules and Basic Auth. Create a list, then select it on a host or location. The first matching IP rule decides access; linked-list ordering is retained. Administrators and operators can edit lists. Referenced resources cannot be deleted.

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

### `rules`

<!-- setting:rules -->
IP rules are evaluated from top to bottom; the first match wins. Use IPv4, IPv6, CIDR (10.0.0.0/8) or all. When rules exist without an all entry, APM appends deny all. With no rules there is no IP restriction.

Format: `array`. Default: `[]`.

Example: `[{"action": "allow", "address": "10.0.0.0/8"}]`.

### `rules.action`

<!-- setting:rules.action -->
allow permits a matching address and deny rejects it. The first matching rule determines the IP decision. Order specific exceptions before broader networks or all.

Format: `string`. Default: `required`. Constraints: allow / deny.

Example: `"allow"`.

### `rules.address`

<!-- setting:rules.address -->
An IP, a CIDR network such as 192.168.1.0/24 or 2001:db8::/32, or all for every address. Host names are not supported. The client IP is determined by the trusted proxy configuration.

Format: `string`. Default: `required`.

Example: `"10.0.0.0/8"`.

### `users`

<!-- setting:users -->
Names of Basic Auth users. New names require passwords in Credentials. Passwords are write-only; adding a name here alone does not create a password. Empty users and rules add no restriction.

Format: `array`. Default: `[]`.

Example: `["alice"]`.

### `satisfy`

<!-- setting:satisfy -->
all requires both the IP rules and Basic Auth checks to pass; any permits access when either check passes. Only configured checks participate. When multiple lists are linked, the first list supplies satisfy.

Format: `string`. Default: `"all"`. Constraints: all / any.

Example: `"all"`.

### `pass_auth`

<!-- setting:pass_auth -->
Forward the client's Authorization header to the backend. Disabled by default: APM clears it. Enable only if the application needs these credentials. With multiple lists, the first list supplies this setting.

Format: `boolean`. Default: `false`.

Example: `false`.

## Example and passwords

For an internal network use allow 10.0.0.0/8, followed by deny all. Put specific exceptions first. Enter one username=password per credentials line. An empty field on edit preserves passwords; a supplied field replaces the entire set. Clear users to remove Basic Auth. Saved passwords cannot be displayed or recovered from the UI.

For multiple lists, the first supplies satisfy and pass_auth. A location with inherit uses host lists, replace requires its own list, and public explicitly removes IP/Basic Auth; external auth_request still applies.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)

## Credentials

### `credentials`

<!-- credential:credentials -->
One username=password per line. Empty preserves passwords; supplied content replaces the entire set. Secrets are write-only.

Format: string. Default: unset; the secret is not displayed after saving.

