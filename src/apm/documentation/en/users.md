# Users

Administrator-only. Create a user with the minimum required role, then configure language and optional OIDC. Users manage MFA in Account security. Role/access changes revoke sessions.

## `email`

<!-- setting:email -->
Unique login email, normalized to lowercase. Required on creation.

## `password`

<!-- setting:password -->
At least 12 characters on creation. Stored hashes are not exposed; use CLI recovery.

## `role`

<!-- setting:role -->
admin manages every section, operator manages routes/ACLs/upstreams without administrative policies, observer reads only. Default observer.

## `enabled`

<!-- setting:enabled -->
Permit login, default true. The last administrator cannot be disabled. Updating a user revokes their sessions.

## `language`

<!-- setting:language -->
Preferred ru/en language, default ru. The interface switch stores a language cookie.

## `oidc_subject`

<!-- setting:oidc_subject -->
OIDC binding as issuer|sub, e.g. https://id.example.com|subject-id. Default null. Users are not automatically bound by email.

## `mfa_enabled`

<!-- setting:mfa_enabled -->
Read-only indicator of an enabled second factor. Changed by confirmed enrollment or local MFA reset.

[Security](security.md) · [CLI](cli.md)
