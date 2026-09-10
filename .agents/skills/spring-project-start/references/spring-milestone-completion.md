# Spring Milestone Completion

Completion closes the loop from approved requirements to applied files and
executed tests. It does not rewrite approved feature or project contracts.
Instead, a cumulative progress ledger records execution state while preserving
the hashes of all upstream evidence.

A milestone is `APPLIED_PREVERIFIED` only when the committed apply transaction,
current cumulative implementation baseline, actual file hashes and modes,
passing isolated verification, and requirement-to-component-to-test links all
match. The full wrapper test command is aggregate execution evidence for the
candidate; it does not claim that every test method ran or that post-apply
runtime verification occurred.

`docs/progress.json` is the machine-readable ledger and `docs/progress.md` is its
user view. The view starts with the completed user value, verification outcome,
remaining unknowns, and the next eligible feature. Candidates are eligible only
when they are not completed or deferred, their dependencies are completed, and
they have no blocking unknown links. Users may accept the recommendation, pick
another candidate, describe the next feature in natural language, or revise an
existing feature.

## Post-apply verification

The common safe plan reruns the wrapper test task from the exact applied source
in a disposable, networkless bubblewrap copy. It exposes the command, timeout,
and all excluded effects before exact approval. A passing report may promote
the milestone to `APPLIED_AND_VERIFIED`; a failed or stale report cannot. DB,
Docker, ports, external integrations, and application startup remain separate
capability-specific verification plans.

The plan is not approval-ready without a local wrapper/dependency cache. The
runner copies only Gradle cache/wrapper or Maven repository content into its
temporary home; user settings and credentials are excluded. Its environment is
cleared, host user homes and common secret-bearing directories are masked, and
secret-like output is redacted and classified `UNKNOWN`. Approval binds both
the structured plan and its exact rendered review. Each failed or unknown run
is immutable evidence; retry with a new attempt output rather than overwriting
it. This common runner records `APPLIED_TEST_ISOLATED`, while DB, application
startup, HTTP smoke, messaging, and distributed integration checks require
their own future verification levels.

V2 consumes the committed Spring code apply result directly. It records a
source/config/baseline manifest and relevant Git snapshot before approval,
stores the command as an executable plus argument array, and runs exactly one
offline wrapper test command. Output is stored separately with a size limit,
hash, truncation flag, and secret/PII redaction status. The runner uses a process
group, TERM grace period, and KILL fallback; an interrupted journal requires
recovery and recovery never silently reexecutes the command. A verified report
sets `readyForMilestoneCompletion`, but keeps `milestoneCompletionAuthorized`
false so progress mutation still requires a separate review and approval.

Each v2 plan path derives a distinct `attemptId`. Approval is consumed before
the attempt allocates or runs its sandbox and cannot be reused; retries require
a new plan, view, and approval, preserving every prior result and log. Relevant
input symlinks are approval blockers. Runner infrastructure errors create a
separate immutable failure receipt when approval was consumed. Recovery checks
PID start ticks and a workspace ownership marker, terminates the owned process
group with TERM then KILL, and never deletes an unproven temporary directory.
