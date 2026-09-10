# Spring Code Apply

Only code with a current, passing isolated verification can reach apply review.
The basic view shows user value, CREATE/UPDATE counts, verification, relevant
Git overlap, unrelated dirty warnings, backup and recovery effects, and actions
that remain excluded. Hashes stay internal.

Apply approval binds the exact dry run, verification report, target context,
current cumulative baseline, and complete file set. Apply revalidates them
immediately before writing. Existing baseline entries outside the current slice
are retained. A user-owned or drifted path is never overwritten.

The transaction records PREPARED, APPLYING, and COMMITTED. Failures recover to
RECOVERED when exact before/after evidence permits it; ambiguous drift produces
RECOVERY_FAILED and forbids overwrite. An active transaction blocks new apply.
Apply and post-apply verification are distinct. A successful apply does not run
target tests, create a Git commit, or push.

## V2 CREATE/REUSE apply

For a passing v2 isolated-verification report, create a user-facing review with
`prepare_spring_code_apply_review_v2.py`. The review is deterministic and binds
the verification report, dry run, cumulative v2 baseline, Git snapshot, exact
CREATE/REUSE set, result path, required disk estimate, backup, and journal.
Only CREATE and unchanged REUSE are supported; UPDATE and DELETE remain blocked.

Approval is recorded only after that exact Markdown review is shown. Apply then
rebuilds the review immediately, takes a non-blocking OS lock, verifies every
hash and mode, copies evidence into a manifest-checked backup, and durably writes
transaction states. It creates parents shallowest-first and source files with
same-filesystem atomic replacement, then writes the merged baseline last.

Application success is `APPLIED_PREVERIFIED`, not test success. The result
report is deliberately written after source commit. If report creation fails,
the source remains committed as `COMMITTED_REPORT_PENDING`; recovery recreates
the report after validating source, baseline, backup manifest, and journal.
Pre-commit failures roll back only exact transaction-created files and empty
parents. Drift or an incomplete rollback is reported for manual review rather
than overwritten.
