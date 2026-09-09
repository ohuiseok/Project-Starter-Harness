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
