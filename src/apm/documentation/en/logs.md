# Angie logs

The Angie logs page shows requests (`access.log`) to all authenticated users. Administrators can also select errors (`error.log`). Newest records appear first; Older and Newer switch pages. Choose 50, 100, 200 or 500 rows per page. Refresh keeps the applied filters. Automatic refresh runs every 5 seconds on the first page while the browser tab is visible.

Enable `access_logs` in [Server settings](runtime.md); it is off by default. Wait for a successful apply, then send requests to a managed host. Records contain time, host, ip, method, path, status, bytes and duration. URI queries are not stored. `mask_log_ips` controls address masking; searches only see the stored address.

## Search and filters

Enter text and select Apply filters or press Enter. Search matches literal text anywhere in the record, including the URI and error message, without case sensitivity. Host and IP match part of the value; the HTTP method matches exactly. All populated filters apply together.

- Requests: host, IP, HTTP method and an exact status (`404`, `502`) or status class (`4xx`, `5xx`).
- Errors: level `emerg`, `alert`, `crit`, `error`, `warn`, `notice`, `info` or `debug`. Host, IP and method work when Angie includes that request context.
- From / To: browser local time, with inclusive bounds. Records without a recognized timestamp are excluded when filtering by time. Standard error log timestamps use the APM server's timezone; existing Angie installations must use the same timezone as APM.

Reset filters clears conditions for the selected log. Applied filters and the current page are saved in the URL for reopening. Incoming records or rotation can change the contents of a page.

Search checks the last 4 MiB, up to 10,000 records, of the **current** file, then filters and paginates the matches. A warning appears when this window is limited. Rotated files are outside this view. Malformed or unstructured lines are displayed as text and remain searchable.

## API

`GET /api/v1/logs/access` and `GET /api/v1/logs/error` accept `q`, `host`, `ip`, `method`, `status`, `level`, `since`, `until`, `limit` (1–500, default 200) and `offset` (0–10,000). Dates use ISO 8601; include an explicit timezone, for example `2026-10-25T10:00:00%2B03:00`. `status` applies to requests and `level` to errors. Responses contain `entries`, `exists`, `scanned`, `matched`, `offset`, `limit`, `has_more` and `truncated`. The server restricts error logs to administrators.

## Storage and existing installations

Managed Angie writes errors at `warn` level and above to `APM_DATA_DIR/logs/error.log`. Existing installations retain the host's logging policy: manually point the required `error_log` to this shared directory to view it in the panel. APM access logs cover its virtual hosts.

Rotation renames files above 20 MB and asks the agent to reopen logs. Cleanup uses `APM_METRICS_RETENTION_DAYS`. Administrative actions are in [Audit](audit.md); configuration application is in [Operations](operations.md).

[Contents](index.md)
