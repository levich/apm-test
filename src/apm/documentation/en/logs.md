# Logs

HTTP access logs are available to all users in the panel and GET /api/v1/logs/access. Enable access_logs in runtime; it is off by default. Records contain time, host, ip, method, path and status. URI queries are not stored. mask_log_ips controls address masking.

Rotation renames files above 20 MB and asks the agent to reopen logs. Cleanup uses APM_METRICS_RETENTION_DAYS. Access logs differ from administrative audit, operations and Angie’s local error.log. For empty logs check access_logs, apply completion and incoming traffic. [Runtime](runtime.md) · [Audit](audit.md)

[Contents](index.md)
