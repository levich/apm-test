# GeoIP rules

Country/ASN restrictions. Enter MaxMind credentials, update MMDB and attach the policy to a host. Requires GeoIP2. Set private/unknown behavior explicitly. Administrator-only.

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

### `countries`

<!-- setting:countries -->
Uppercase ISO 3166-1 alpha-2 country codes, one per line, such as RU or DE. Requires a loaded GeoIP database.

Format: `array`. Default: `[]`.

Example: `["DE"]`.

### `asns`

<!-- setting:asns -->
Autonomous system numbers without the AS prefix, one per line, in the range 1–4294967295. Requires the ASN database.

Format: `array`. Default: `[]`.

Example: `[64512]`.

### `database_version`

<!-- setting:database_version -->
Read-only version of installed GeoIP databases. Updated by Update MMDB; not entered manually.

Format: `string`. Default: `""`.

Example: `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`.

### `mode`

<!-- setting:mode -->
allow permits listed countries/ASNs and denies others; deny blocks listed entries. Configure private and unknown address behavior separately.

Format: `string`. Default: `"deny"`. Constraints: allow / deny.

Example: `"deny"`.

### `allow_private`

<!-- setting:allow_private -->
Allow private and local IPs independently of geography rules. Useful for internal services and checks.

Format: `boolean`. Default: `true`.

Example: `true`.

### `allow_unknown`

<!-- setting:allow_unknown -->
Allow addresses whose country/ASN is unknown to the database. Disabling may block new or unmapped networks.

Format: `boolean`. Default: `true`.

Example: `true`.

## Workflow example

Create a clearly named resource, complete required settings and save. Confirm apply completion in Operations. If angie -t fails, fix settings or dependencies; the previous working configuration remains. Observers read data; administrators delete resources no longer referenced.

[Operations](operations.md) · [System settings](environment.md) · [Contents](index.md)

## Credentials

### `account_id`

<!-- credential:account_id -->
MaxMind account ID for downloading GeoLite2 Country and ASN databases.

Format: string. Default: unset; the secret is not displayed after saving.

### `license_key`

<!-- credential:license_key -->
MaxMind license key permitted to download databases, used by the MMDB update action.

Format: string. Default: unset; the secret is not displayed after saving.

