# Certificates

Upload custom PEM/key material or create a managed ACME certificate. DNS-01 requires a DNS profile first. Routes reference certificates by ID. Creation, upload and manual reissuance require an administrator.

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
Certificate SAN domains without scheme/port, one per line. Wildcards cover one subdomain level and require DNS-01; add the apex domain separately.

Format: `array`. Default: `[]`.

Example: `["app.example.com"]`.

### `mode`

<!-- setting:mode -->
custom uploads PEM and key manually; http uses ACME HTTP-01 with public TCP/80; dns uses DNS-01 with a DNS profile and supports wildcards.

Format: `string`. Default: `"custom"`. Constraints: custom / http / dns.

Example: `"custom"`.

### `dns_profile_id`

<!-- setting:dns_profile_id -->
Previously created DNS account profile. DNS-01 needs permission to update TXT records in the domain's zone. Create and test the profile in DNS providers; its credentials are not entered in this host form.

Format: `string / null`. Default: `null`.

Example: `"<resource-id>"`.

### `email`

<!-- setting:email -->
Account owner email. For certificates it is sent to the ACME CA; for users it is the login. Use an address you control.

Format: `string`. Default: `""`.

Example: `"admin@example.com"`.

### `terms_agreed`

<!-- setting:terms_agreed -->
Explicit agreement to the ACME CA terms. Required for a managed certificate and manual reissuance.

Format: `boolean`. Default: `false`.

Example: `false`.

### `server`

<!-- setting:server -->
ACME directory URL. Defaults to production Let’s Encrypt. Use a staging CA for tests; browsers do not trust its certificates.

Format: `string`. Default: `"https://acme-v02.api.letsencrypt.org/directory"`.

Example: `"https://acme-v02.api.letsencrypt.org/directory"`.

### `profile`

<!-- setting:profile -->
ACME CA profile name passed as --required-profile. Leave empty if the CA does not require a profile.

Format: `string / null`. Default: `null`.

Example: `"your-ca-profile"`.

### `key_type`

<!-- setting:key_type -->
Certificate key type: ecdsa or rsa. Reissuance uses this choice; consider client compatibility.

Format: `string`. Default: `"ecdsa"`. Constraints: ecdsa / rsa.

Example: `"ecdsa"`.

### `reuse_key`

<!-- setting:reuse_key -->
Ask Certbot to retain the key during renewal. Off by default, allowing key rotation with the certificate.

Format: `boolean`. Default: `false`.

Example: `false`.

### `must_staple`

<!-- setting:must_staple -->
Request the TLS Must-Staple extension. Clients may require OCSP stapling; enable only with a suitable CA and working stapling.

Format: `boolean`. Default: `false`.

Example: `false`.

### `status`

<!-- setting:status -->
Read-only system processing state. The separate file and validity check reports whether the installed certificate is usable.

Format: `string`. Default: `"pending"`. Constraints: pending / ready / error.

Example: `"pending"`.

### `fingerprint`

<!-- setting:fingerprint -->
System SHA-256 identifier for a PEM version. Read-only; paths are versioned and old revisions remain available for rollback.

Format: `string / null`. Default: `null`.

Example: `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`.

### `expires_at`

<!-- setting:expires_at -->
Read-only expiry as a UTC Unix timestamp in seconds. The table displays local time and remaining days.

Format: `integer / null`. Default: `null`.

Example: `1800000000`.

## Status, reissuance and replacement

Issuance state is separate from installed certificate validity. The table shows start/expiry and remaining days, warning within 30 days. Checks cover PEM, matching key, current validity and domain SAN including one-level wildcards. Missing files, mismatches and expiry have separate statuses.

Administrators can Reissue enabled http/dns certificates using POST /api/v1/resources/certificates/{id}/renew. Issuance is forced (--force-renewal) even before expiry; CA rate limits still apply. A pending/running issue blocks another request (HTTP 409). Success installs a new version and queues apply. Failure retains previous files. For custom certificates upload replacement PEM and matching key. Scheduled checks are separate and use --keep-until-expiring.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)

## Credentials

### `eab_kid`

<!-- credential:eab_kid -->
External Account Binding key ID of the ACME CA; requires eab_hmac_key. Leave empty for ordinary Let’s Encrypt.

Format: string. Default: unset; the secret is not displayed after saving.

### `eab_hmac_key`

<!-- credential:eab_hmac_key -->
ACME CA EAB HMAC key paired with eab_kid, passed to Certbot using a temporary 0600 file.

Format: string. Default: unset; the secret is not displayed after saving.

