# Audit

Administrator log of changes and authentication events. GET /api/v1/audit returns up to 200 recent records: created_at, actor, action, object_id and detail. API access is admin-only.

Use audit to establish who changed settings, and Operations for apply results. Details contain actions and identifiers without passwords or keys. Deleting a resource preserves old audit records. Recover access using the local CLI on the verified server.

[Contents](index.md)
