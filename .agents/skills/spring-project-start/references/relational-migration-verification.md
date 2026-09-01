# Isolated Relational Migration Verification

This milestone executes an ordered chain of already-applied, baseline-owned
versioned Flyway migrations against a disposable PostgreSQL container. It
requires a separate exact-plan
approval because Docker image pulls, containers, a private network, processes,
and temporary memory are real host-side effects.

The runner uses pinned PostgreSQL and Flyway image references, no published
ports, no persistent volume, a bounded tmpfs data directory, a random ephemeral
credential passed through a mode-0600 temporary env file, command timeouts, and
unique labeled resource names. It stages only the exact approved chain, runs
`flyway migrate`, `flyway validate`, and JSON `flyway info`, then compares the
successful versioned history with the approved versions and descriptions. It
records only redacted bounded output and always attempts to
remove the database container and network. It never reads application secrets,
connects to a configured or production database, starts the project's Compose
service, or changes target source files. It writes only its evidence report.

Before creating Docker resources, the runner atomically records their exact
names and required label in `.starter-harness/verification/pending.json`. A
pending journal blocks another run. After an ordinary success or failure, the
result report is written atomically before the journal is removed. If the
process is interrupted or cleanup is incomplete, use
`recover_relational_migration_verification.py --target <target-path>`. Recovery
validates the journal, inspects every existing resource for the exact Harness
label, refuses to remove an unlabeled resource, and preserves recovery evidence
under `.starter-harness/verification/recovered/`.

Docker tmpfs is removed with the container, but on hosts configured with swap
the operating system may write memory pages to swap. The plan view must disclose
this limitation.

Plan version 3 requires a non-empty `migrations` array. Every item fixes the
canonical numeric-dot version, Flyway description, target-relative path, and
SHA-256. Versions must be unique and ascending but need not be contiguous. Each
path must be a supported `V...__....sql` file owned by the current relational
baseline. Repeatable, undo, baseline-on-migrate, repair, and out-of-order flows
are outside this milestone. A legacy plan must be migrated into a separate
version 3 draft and explicitly approved again.
Within the selected migration directory, the plan must include every
baseline-owned versioned migration at or below its target version; this prevents
an intermediate dependency from being silently omitted. A different store or
service migration directory requires its own verification plan.

Plan version 3 additionally pins the approved physical contract and physical
model. After Flyway history validation, the runner reads only PostgreSQL system
catalogs from the disposable database and compares normalized tables, columns,
types, nullability, defaults, primary keys, unique columns, foreign keys,
checks, and non-constraint indexes. Both normalized documents receive SHA-256
fingerprints and every mismatch is reported by a stable property path.

Successful verification proves that the approved migration chain executes,
validates, matches Flyway's successful history, and materializes the approved
physical schema in the selected isolated
PostgreSQL/Flyway image pair. It does not
prove production permissions, production data compatibility, lock duration,
rollback behavior, performance, or deployment success.

The accepted Flyway repositories are Redgate-published `redgate/flyway` and
`flyway/flyway`. Prefer an exact patch-version tag that is actually published;
the runner pulls it, records its image ID and repository digest, and executes
the immutable image ID rather than resolving the tag again.
