# Local CLI

Run commands on the APM server with the same APM_* values and data directory. Local deployment-owner privileges are required. Enter passwords interactively. Use apm COMMAND --help for usage.

## `apm serve`

<!-- command:serve -->
Run manager; --host defaults to 0.0.0.0, --port to 8181. Publish the backend on loopback/private networks only.

<!-- option:serve.host -->
<!-- option:serve.port -->

## `apm worker`

<!-- command:worker -->
Run the queue, maintenance and backend monitoring. --once processes a single job without continuous monitoring.

<!-- option:worker.once -->

## `apm agent`

<!-- command:agent -->
Run the local Unix agent in Angie’s network. Requires Angie validation/reload privileges.


## `apm bootstrap-agent`

<!-- command:bootstrap-agent -->
Prepare bootstrap TLS and initial includes. Does not replace the root Angie configuration in existing mode.


## `apm pre-run`

<!-- command:pre-run -->
Execute local deployment hooks from APM_PRE_RUN_DIR. HTTP API cannot create hooks.


## `apm setup-token`

<!-- command:setup-token -->
Print the one-time setup token locally. Unavailable after creating the first administrator.


## `apm migrate`

<!-- command:migrate -->
Apply current schema migrations. Upgrading an existing schema creates a backup first.


## `apm backup-password`

<!-- command:backup-password -->
Interactively store an archive password of at least 16 characters. Do not pass it in process arguments.


## `apm backup`

<!-- command:backup -->
Create an encrypted backup with manager and worker stopped. Requires a stored archive password.


## `apm restore`

<!-- command:restore -->
ARCHIVE argument is the .apm path; password input is hidden. Stop manager and worker first; the previous directory is retained.

<!-- option:restore.archive -->

## `apm reset-password`

<!-- command:reset-password -->
EMAIL argument; enter a new password of at least 12 characters using hidden input. --reset-mfa clears TOTP/recovery too. All sessions are revoked.

<!-- option:reset-password.email -->
<!-- option:reset-password.reset_mfa -->

## `apm resume-applies`

<!-- command:resume-applies -->
Resume applies after locally repairing a rollback failure. Cannot run while an unresolved apply-journal.json exists.


## `apm export-npm`

<!-- command:export-npm -->
OUTPUT is a new snapshot file. Choose exactly one source: --sqlite PATH or --postgres (hidden DSN input). --certificates PATH adds PEM from live/npm-ID. Export is read-only.

<!-- option:export-npm.output -->
<!-- option:export-npm.sqlite -->
<!-- option:export-npm.postgres -->
<!-- option:export-npm.certificates -->

## `apm gateway`

<!-- command:gateway -->
Read-only Docker gateway; --host 0.0.0.0, --port 2375. Only required discovery read requests are allowed; keep the port off the public internet.

<!-- option:gateway.host -->
<!-- option:gateway.port -->

