# CrowdSec / AppSec

CrowdSec/AppSec protection. Prepare Lua modules and services, enter endpoints and keys, then attach one shared profile to the required hosts. AppSec requires request_buffering. Administrator-managed.

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

### `lapi_url`

<!-- setting:lapi_url -->
CrowdSec LAPI origin reachable by Angie. Supply api_key in profile secrets; requires the Lua integration.

Format: `string`. Default: `"http://127.0.0.1:8080"`.

Example: `"http://127.0.0.1:8080"`.

### `appsec_url`

<!-- setting:appsec_url -->
CrowdSec AppSec origin reachable by Angie. Used when appsec is enabled; check its address and port separately from LAPI.

Format: `string`. Default: `"http://127.0.0.1:7422"`.

Example: `"http://127.0.0.1:7422"`.

### `appsec`

<!-- setting:appsec -->
Enable AppSec request inspection. Linked hosts require request_buffering=true; one shared CrowdSec profile per server.

Format: `boolean`. Default: `true`.

Example: `true`.

### `observe`

<!-- setting:observe -->
Observe CrowdSec decisions without blocking. Use to validate integration before enforcing decisions.

Format: `boolean`. Default: `false`.

Example: `false`.

### `failure_action`

<!-- setting:failure_action -->
When the protection service fails, deny rejects the request and allow passes it. Choose the required failure behavior.

Format: `string`. Default: `"deny"`. Constraints: deny / allow.

Example: `"deny"`.

### `captcha_provider`

<!-- setting:captcha_provider -->
CAPTCHA provider: off, recaptcha, hcaptcha or turnstile. An enabled provider needs site_key and secret_key.

Format: `string`. Default: `"off"`. Constraints: off / recaptcha / hcaptcha / turnstile.

Example: `"off"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)

## Credentials

### `api_key`

<!-- credential:api_key -->
CrowdSec bouncer API key for LAPI. Create it in CrowdSec and enter it only in the profile secret.

Format: string. Default: unset; the secret is not displayed after saving.

### `site_key`

<!-- credential:site_key -->
Site key of the selected CAPTCHA provider, required with secret_key when CAPTCHA is enabled.

Format: string. Default: unset; the secret is not displayed after saving.

### `secret_key`

<!-- credential:secret_key -->
CAPTCHA provider secret matching site_key; write-only.

Format: string. Default: unset; the secret is not displayed after saving.

