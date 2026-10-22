# ECH keys

Encrypted ClientHello: create a profile, generate a key, publish ECHConfigList in a DNS HTTPS record and confirm DNS. Then select the profile in a TLS policy. Requires compatible modules/library; administrator-only.

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

### `public_name`

<!-- setting:public_name -->
Outer ECH name, such as public.example.com. Requires ECH support and the corresponding DNS configuration.

Format: `string`. Default: `required`.

Example: `"public.example.com"`.

### `domains`

<!-- setting:domains -->
Host names without a protocol, port or path, one per line. For example: app.example.com. DNS records are configured separately. A wildcard certificate such as *.example.com requires DNS-01 validation.

Format: `array`. Default: `required`.

Example: `["app.example.com"]`.

### `dns_profile_id`

<!-- setting:dns_profile_id -->
Previously created DNS account profile. DNS-01 needs permission to update TXT records in the domain's zone. Create and test the profile in DNS providers; its credentials are not entered in this host form.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `status`

<!-- setting:status -->
Read-only ECH state: pending before generation, awaiting_dns while DNS publication is pending, ready after confirmation for use in a TLS policy.

Format: `string`. Default: `"pending"`. Constraints: pending / awaiting_dns / ready.

Example: `"pending"`.

### `config`

<!-- setting:config -->
System-generated ECHConfigList to publish in a DNS HTTPS record. Created by key generation; read-only.

Format: `string`. Default: `""`.

Example: `"<generated ECHConfigList>"`.

### `current_key`

<!-- setting:current_key -->
Active ECH key identifier, changed after successful DNS confirmation.

Format: `string`. Default: `""`.

Example: `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`.

### `previous_key`

<!-- setting:previous_key -->
Previous ECH key for gradual rotation, retained alongside the current key; read-only.

Format: `string`. Default: `""`.

Example: `null`.

### `pending_key`

<!-- setting:pending_key -->
A generated ECH key not yet confirmed in DNS. Publish its HTTPS record and run DNS confirmation.

Format: `string`. Default: `""`.

Example: `"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)
