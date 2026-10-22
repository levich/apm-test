# Operations

Saving a resource records desired state and queues work. The worker processes jobs sequentially; issuance and application are separate jobs. pending means queued, running means processing, succeeded means completed, failed means an error. The page refreshes every 5 seconds unless an editor is open. All users can read it.

Applying generates named fragments, runs angie -t, switches current, reloads and confirms generation. Candidate errors preserve the previous version. If rollback fails, further applies stop: repair Angie and the apply journal locally, then run apm resume-applies. Other necessary work such as DNS cleanup continues.

Operations show the resource name, outcome, reason and next step. Technical details include ID, type and safe diagnostics; private snapshots and tokens are not exposed. New jobs retain context after resource rename/deletion. Historical jobs without context show a generic title. Backend monitoring failures are separate and do not roll back administrative configuration.

[Contents](index.md)
