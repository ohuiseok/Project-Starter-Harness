# Isolated Relational Migration Verification

This milestone executes only an already-applied, baseline-owned Flyway migration
against a disposable PostgreSQL container. It requires a separate exact-plan
approval because Docker image pulls, containers, a private network, processes,
and temporary memory are real host-side effects.

The runner uses pinned PostgreSQL and Flyway image references, no published
ports, no persistent volume, a bounded tmpfs data directory, a random ephemeral
credential passed through a mode-0600 temporary env file, command timeouts, and
unique labeled resource names. It runs `flyway migrate` followed by
`flyway validate`, records only redacted bounded output, and always attempts to
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

Successful verification proves that the approved migration executes and
validates in the selected isolated PostgreSQL/Flyway image pair. It does not
prove production permissions, production data compatibility, lock duration,
rollback behavior, performance, or deployment success.

The accepted Flyway repositories are Redgate-published `redgate/flyway` and
`flyway/flyway`. Prefer an exact patch-version tag that is actually published;
the runner pulls it, records its image ID and repository digest, and executes
the immutable image ID rather than resolving the tag again.
