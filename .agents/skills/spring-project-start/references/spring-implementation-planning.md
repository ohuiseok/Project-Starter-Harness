# Spring Implementation Planning

Implementation planning converts approved feature, technology, API, and optional
database evidence into a component graph. It never generates or changes source,
build, configuration, migration, or test files.

Before building that graph, create an HTTP API Spring mapping for every selected
operation. The mapping binds approved contract and OpenAPI hashes, scans existing
Java/Kotlin symbols, and records architecture, MVC/WebFlux, DTO style, mapping
style, and test client with provenance. Exact literal Controller endpoints may
be reused. Ambiguous annotations, inherited mappings, generated sources, and
unproven project-evidence decisions remain `UNKNOWN`; duplicate endpoint owners
are conflicts.

Mapping schema v2 is reconstructed rather than merely shape-validated. It
limits source count and bytes, snapshots only relevant symbols, distinguishes
unrelated changes, and treats dirty reuse as blocking. Controller, DTO, and
service paths reflect the selected architecture. OpenAPI body and response
shapes decide whether DTOs exist, while security schemes, scopes, CSRF, status
codes, and validation cases determine tests. The implementation-plan creator
must consume a current approval receipt; no legacy direct path may bypass it.
Revisions form an immutable previous-hash chain and only its latest uncancelled
head can be approved. Legacy v1 artifacts are rebuilt as separate v2 reviews.

The user view uses progressive disclosure: summary and recommended structure,
API-by-API responsibilities and tests, conflicts/UNKNOWN, then choices to accept,
edit one item, enter another approach in natural language, or cancel. An API
mapping never creates persistence components without an approved data contract,
never exposes an entity as an API DTO, and never lets one microservice access
another service's repository directly. It authorizes only preparation of the
later component plan.

The first milestone supports one Java, Spring MVC, Spring Data JPA, PostgreSQL,
single-module REST CREATE operation. Existing target structure wins over a new
architecture recommendation. User-owned occupied paths are blocking conflicts;
the first milestone never extends them.

The basic user view starts with the user flow, change counts, transaction, error
behavior, tests, and actionable conflicts. File paths and hashes are details.
Every acceptance criterion and business rule needs implementation and automated
test coverage. API DTOs and JPA entities are separate components. A write service
owns the transaction boundary. Approval authorizes only a later code dry run.
