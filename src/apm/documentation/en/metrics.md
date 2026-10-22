# Metrics

Shows the latest available Angie metrics and a GoAccess link. All users can read it. The worker collects metrics during periodic maintenance; retention is APM_METRICS_RETENTION_DAYS, capped at 10080 points. Points contain time, connections and HTTP requests.

GoAccess needs compose.analytics.yaml and runtime access_logs=true, analytics=true. Without a reachable agent data may be missing or old; check collection time. These metrics do not replace per-backend checks.

[Contents](index.md)
