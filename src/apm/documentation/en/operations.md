# Operations

Saving a resource records desired state and queues work. The worker processes jobs sequentially; issuance and application are separate jobs. pending means queued, running means processing, succeeded means completed, failed means an error. The page refreshes every 5 seconds unless an editor is open. All users can read it.

Applying generates named fragments, runs angie -t, switches current, reloads and confirms generation. Candidate errors preserve the previous version. If rollback fails, further applies stop: repair Angie and the apply journal locally, then run apm resume-applies. Other necessary work such as DNS cleanup continues.

Operations show the resource name, outcome, reason and next step. Technical details include ID, type and safe diagnostics; private snapshots and tokens are not exposed. New jobs retain context after resource rename/deletion. Historical jobs without context show a generic title. Backend monitoring failures are separate and do not roll back administrative configuration.

[Contents](index.md)


Safe application is enabled by default. After reload, a manual change enters awaiting_confirmation. Every panel page shows checks, a countdown and Confirm access / Roll back now buttons. Confirmation requires an administrator or the initiating operator session. In managed mode, confirmation must pass through the candidate Angie configuration; the direct manager backend cannot confirm. Refreshes and background requests never confirm changes.

Deadline expiry, cancellation, agent restart or three consecutive required-check failures restore the previous revision. The agent and independent watchdog work without manager/worker. Subsequent applies wait for a decision; other jobs, including DNS cleanup, continue. After rollback, applies remain paused until local recovery. Desired resources remain drafts; users, audit records and the whole database are not rolled back.

Checks establish a baseline before activation. Previously failing additional checks remain visible in baseline and do not count as regressions for manual changes. The panel check is always required. Automatic changes (discovery, certificates and other internal jobs) require all baseline and post-switch checks to pass.

Warnings from angie -t with exit code 0 do not block activation and appear in operations and the JSON API. Known warnings have safe descriptions and, when available, a revision file/line. Arbitrary stderr is never persisted because it can contain secrets. Unknown warnings require local error.log inspection or a manual angie -t. Nonzero exit codes reject the configuration before switching.

In existing mode, recovery covers APM includes; the owner's root configuration is outside rollback. The panel check uses APM_PUBLIC_URL/health/live with normal TLS verification. Local checks cannot replace external DNS, firewall and client reachability checks.


The safe-mode indicator is always visible: enabled/disabled, agent availability and the independent watchdog. An old agent reports that it needs an update rather than silently hiding status. Replacing the checkout is insufficient for existing installations: reinstall the package in the host .venv, restart apm-agent and apm-safety-watchdog, and rebuild containers from the same sources.
