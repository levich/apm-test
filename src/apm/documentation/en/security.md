# Account security

The current user can configure TOTP. Enter the current password, enroll, add the displayed otpauth URI to an authenticator and confirm a one-time code. Store recovery codes: they are displayed once after confirmation. The URI contains a secret; do not publish it.

After password login supply TOTP or an unused recovery code. Local administrator recovery uses apm reset-password EMAIL --reset-mfa, revoking every session for that user. Enable OIDC through system settings and bind oidc_subject to an existing user first. [Users](users.md) · [System settings](environment.md)

[Contents](index.md)
