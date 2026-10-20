# Contributing

Use Python 3.13 and `uv sync --frozen --group dev --no-editable`. Run `pytest` and `ruff check src tests scripts`. Compiler or lifecycle changes also require the real binary scenario in `scripts/check_angie.py`. UI changes require `scripts/browser_check.py` with an isolated empty data directory.

Existing-Angie compiler or lifecycle changes also require `scripts/check_existing_angie.py --binary /path/to/angie --conf-dir /path/to/conf --work ./test-results/existing-angie`. It runs an isolated instance with legacy HTTP configuration and verifies APM HTTP/TCP traffic plus preservation after rejected APM and legacy configuration changes.

Keep original application code under MIT; preserve dependency licenses. Do not copy NPMPlus code. Never include credentials, setup tokens, private keys, databases or real exports in fixtures or pull requests.

Treat `docs/COMPATIBILITY.md` as the release checklist. A generated directive or an available module does not establish feature compatibility. Record the exact Angie edition/build, TLS library, platform and network/failure tests before changing a status to verified.

New migrations must preserve prior schemas, back up before upgrade, and keep upgrade/restore tests. A rollback means an old image plus the matching backup. Do not add automatic down-migrations for production data.

When adding a DNS provider, implement account serialization where required, least-destructive TXT changes, ownership-aware cleanup and live ACME staging tests. Unit tests with mocked HTTP are necessary but not sufficient for qualification.
