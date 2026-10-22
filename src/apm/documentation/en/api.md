# API and computed status

The API requires cookie authentication. Mutations require X-CSRF-Token; updating/deleting resources requires If-Match with the current version. Roles are checked server-side. Save responses contain operation_id/revision_id: wait for the operation. Full OpenAPI is admin-only at /api/docs.

GET /api/v1/resources/proxy-hosts adds health (status, checked_at, checks), ssl (configured, usable), certificate_info and active_operation. Certificate lists add certificate_info and active_operation. These are computed, outside editable data and private snapshots. health.status: up/partial/down/unknown/disabled. certificate_info.status: valid/expiring/expired/not_yet_valid/key_mismatch/domain_mismatch/invalid_files/missing/disabled. Dates use Unix UTC seconds; remaining_days rounds upward. active_operation contains id/status or null.

POST /api/v1/resources/certificates/{id}/renew is admin-only: 202 with operation_id when queued, 409 for active issuance, 422 for custom/disabled or missing prerequisites. GET /api/v1/operations[/{id}] retains kind/status/error/result and adds title/status_label/message/next_step/subject, localized to the UI language. Monitoring calls use the Unix agent, never browser-to-backend requests.
