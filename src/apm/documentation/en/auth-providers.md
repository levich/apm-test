# External authentication

External auth_request services. Deploy a compatible service, enter its origin and sign-in URL, then attach the profile to a host/location. APM does not install the authentication service. Profiles are administrator-managed.

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

### `provider`

<!-- setting:provider -->
auth_request service type. APM selects endpoints and allowed headers for Authelia, Authentik, OAuth2 Proxy, TinyAuth, VoidAuth or Anubis.

Format: `string`. Default: `required`. Constraints: authelia / authentik / oauth2proxy / tinyauth / voidauth / anubis.

Example: `"authelia"`.

### `url`

<!-- setting:url -->
HTTP(S) origin of the external authentication service without a query or path. APM appends the provider endpoint; Angie must reach it.

Format: `string`. Default: `required`.

Example: `"https://auth.example.com"`.

### `signin_url`

<!-- setting:signin_url -->
Full external provider sign-in URL, used as the redirect destination for unauthenticated clients.

Format: `string`. Default: `required`.

Example: `"https://auth.example.com/login"`.

### `redirect_login`

<!-- setting:redirect_login -->
Redirect auth_request 401 responses to signin_url. Disable for APIs that should return an authentication status instead of a login page.

Format: `boolean`. Default: `true`.

Example: `true`.

### `identity_headers`

<!-- setting:identity_headers -->
Allowed identity headers from the authentication service response. Other known identity headers are cleared to prevent client impersonation.

Format: `array`. Default: `["Remote-User", "Remote-Email", "Remote-Groups"]`. Constraints: Remote-User / Remote-Email / Remote-Groups / X-Auth-Request-User / X-Auth-Request-Email / X-Authentik-Username / X-Authentik-Email / X-Authentik-Groups.

Example: `["Remote-User", "Remote-Email", "Remote-Groups"]`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)


Identity variables use short unique names compatible with the default variables_hash_bucket_size=64 on Linux. Enabling external authentication does not require increasing the global hash bucket size. HTTPS auth_request upstreams receive their hostname as SNI.
