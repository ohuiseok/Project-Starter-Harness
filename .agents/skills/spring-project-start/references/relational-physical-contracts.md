# Relational Physical Contracts

Use this workflow only after a logical relational `PERSISTENCE CREATE` contract
is approved and current. It converts logical identities into a database-specific
physical design and execution plan without generating migrations, source files,
containers, volumes, or databases.

## Truth And Boundaries

The physical-model JSON is an approved design input. It is not the runtime schema
source of truth. For the ready PostgreSQL + Flyway adapter, the later versioned
Flyway migration becomes the execution source. A future dry run must reconstruct
the expected schema from that migration and compare it with this physical design.

Physical-contract approval does not approve file application, Docker startup,
volume creation or deletion, migration execution, or database access. These are
separate later approvals. Database migration is never described as having the
same atomic rollback guarantee as Harness file application.

## Reference Adapter

`postgresql-flyway` is the first end-to-end reference adapter. Other combinations
remain visible in the capability registry as `PLANNED`, `REVIEW`, or
`NOT_IMPLEMENTED`; the Harness must not silently render them as PostgreSQL.

The contract covers tables, columns, SQL types, primary and unique keys, foreign
keys, checks, indexes with query justification, stable logical-to-physical refs,
invariant enforcement, migration recovery classification, and provisioning
intent. PostgreSQL identifiers use unquoted snake_case, avoid reserved names,
and remain within 63 bytes.

## Provisioning Safety

Docker plans use a pinned image, target-relative future Compose path, isolated
service and volume names, secret names only, execution-time port checking,
`autoStart: false`, and `destructiveCleanupAllowed: false`. Testcontainers never
persists generated credentials or enables reusable containers by default. No
password examples or values are generated.

## Gates

Approval requires exact hashes for the approved logical metadata/model and the
physical model, a `READY` adapter, complete logical coverage, compatible types,
resolved invariant enforcement, justified indexes, safe identifiers, no stale
input, and explicit non-execution flags. Approval changes only physical metadata
and its derived Markdown view.
