# DNS providers

DNS API access for ACME and ECH. Select the provider, zone and credentials, save and run a test. Testing confirms read access, not write permissions. Only administrators manage profiles.

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
DNS API: Webnames, Yandex Cloud DNS, REG.RU, Selectel v2 or Cloud.ru Evolution. Supply the selected provider credentials listed below.

Format: `string`. Default: `required`. Constraints: webnames / yandex / regru / selectel / cloudru.

Example: `"webnames"`.

### `zone`

<!-- setting:zone -->
DNS zone without a scheme, such as example.com. Certificate domains must be in a zone accessible to these credentials.

Format: `string`. Default: `required`.

Example: `"example.com"`.

### `zone_id`

<!-- setting:zone_id -->
The provider API zone identifier when required. This is not a domain name; obtain it from the provider console.

Format: `string`. Default: `""`.

Example: `"your-zone-id"`.

### `ttl`

<!-- setting:ttl -->
TTL of the ACME TXT record in seconds. Lower values help record changes; respect provider limits.

Format: `integer`. Default: `300`. Constraints: minimum=60; maximum=86400.

Example: `300`.

### `propagation_timeout`

<!-- setting:propagation_timeout -->
Maximum TXT propagation wait in seconds. Exceeding it fails issuance; cleanup removes the challenge record.

Format: `integer`. Default: `600`. Constraints: minimum=30; maximum=3600.

Example: `600`.

### `discovery_allowed`

<!-- setting:discovery_allowed -->
Allow Docker discovery to use this DNS profile. Discovery also needs its environment switch and network/domain allowlists.

Format: `boolean`. Default: `false`.

Example: `false`.

### `operator_allowed`

<!-- setting:operator_allowed -->
Allow operators to select this profile for DNS-01 requests. Secrets remain write-only and administrator-managed.

Format: `boolean`. Default: `false`.

Example: `false`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)

## Credentials

Webnames and REG.RU: username/password; Yandex: iam_token or service_account_id/key_id/private_key; Selectel v2: token or username/password/domain_name/project_id; Cloud.ru: token or key_id/secret.

### `username`

<!-- credential:username -->
Webnames/REG.RU API username or Selectel IAM user. Use a dedicated account limited to required zones.

Format: string. Default: unset; the secret is not displayed after saving.

### `password`

<!-- credential:password -->
Webnames/REG.RU API password or Selectel IAM password. Write-only and encrypted; do not publish it in Docker labels.

Format: string. Default: unset; the secret is not displayed after saving.

### `iam_token`

<!-- credential:iam_token -->
Temporary Yandex Cloud IAM token. An alternative to service-account keys; refresh it before expiry.

Format: string. Default: unset; the secret is not displayed after saving.

### `service_account_id`

<!-- credential:service_account_id -->
Yandex Cloud service-account ID with DNS-zone access.

Format: string. Default: unset; the secret is not displayed after saving.

### `key_id`

<!-- credential:key_id -->
Yandex service-account key ID or Cloud.ru access key ID, paired with the corresponding private key/secret.

Format: string. Default: unset; the secret is not displayed after saving.

### `private_key`

<!-- credential:private_key -->
Yandex service-account private key PEM. Include the complete BEGIN/END lines and line breaks.

Format: string. Default: unset; the secret is not displayed after saving.

### `token`

<!-- credential:token -->
Selectel v2 or Cloud.ru API token, an alternative to its IAM/access-key fields.

Format: string. Default: unset; the secret is not displayed after saving.

### `domain_name`

<!-- credential:domain_name -->
Selectel IAM domain name, not the certificate DNS zone. Required for username/password token acquisition.

Format: string. Default: unset; the secret is not displayed after saving.

### `project_id`

<!-- credential:project_id -->
Selectel project ID used for IAM authentication.

Format: string. Default: unset; the secret is not displayed after saving.

### `secret`

<!-- credential:secret -->
Cloud.ru Evolution secret access key paired with key_id. Not an APM user password.

Format: string. Default: unset; the secret is not displayed after saving.

