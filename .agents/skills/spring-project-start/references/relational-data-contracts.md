# Relational Data Contracts

Use this workflow for an approved route v2 `PERSISTENCE` instance with
disposition `CREATE`. This first milestone designs a logical relational model;
it does not create tables, migrations, entities, containers, or databases.

## Source Of Truth

The relational data-model JSON owns logical entities, stable field identities,
relationships, lifecycle, sensitivity, invariants, the future physical-artifact
strategy, and local runtime-provisioning intent. Contract metadata owns route
linkage, target identity, evidence, traceability, and approval. Markdown and
Mermaid ERD are derived views and are never independent sources.

The model is not a replacement for a project's eventual Flyway, Liquibase,
declarative SQL, or externally managed schema source. A later physical-design
milestone must select and generate or link that source explicitly.

## UX And Decisions

Show business entities, their meaning, relationships, lifecycle, sensitive-data
classification, and feature links before physical database details. Ask one
material question at a time. Local database setup offers Docker Compose,
Testcontainers, both, externally managed, deferred, and custom choices. Custom
input is first-class.

Docker selection records a pinned image reference, a future target-relative
Compose path, and secret *names* only. It never stores credential values and
does not start Docker during contract design. Testcontainers is a verification
strategy and does not silently replace a developer's chosen local environment.

## Gates

Approval requires an approved design route, a current feature and technology
profile, stable unique entity/field/relationship IDs, an identifier for every
entity, valid relationship endpoints and both-side cardinalities, resolved lifecycle and sensitivity,
feature traceability, and a resolved provisioning decision. Docker-based
strategies require a known relational engine and an explicitly pinned image.
Metadata records the exact model digest; any later model edit makes the approved
contract stale even when its requirement links did not change.

Approval permits physical design planning only. It does not authorize migration,
Entity, Repository, Docker Compose, configuration, database startup, or source
application.

Materialize an agent-prepared model and derived metadata with
`create_relational_data_contract.py`. Validate with
`validate_relational_data_contract.py`, render with
`render_relational_data_contract.py`, and after explicit user confirmation use
`record_relational_data_contract_approval.py`. Approval rechecks the exact model,
route inputs, metadata, and Markdown atomically while leaving the model unchanged.
