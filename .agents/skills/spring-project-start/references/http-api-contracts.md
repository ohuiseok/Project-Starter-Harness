# HTTP API Contracts

Use this workflow only for an approved route v2 instance whose kind is
`HTTP_API` and disposition is `CREATE`. `EXTEND` and `REUSE` require observed
existing interface evidence and are separate milestones.

## Source Of Truth

The OpenAPI document owns paths, methods, parameters, request and response
schemas, examples, status codes, and security schemes. Contract metadata owns
route linkage, target identity, approval, evidence, and derived traceability.
Do not manually duplicate interface fields in metadata.

The initial deterministic implementation accepts OpenAPI JSON. JSON is an
OpenAPI serialization and avoids silently accepting YAML that the local runtime
cannot parse. A later YAML adapter must produce the same assessment and must not
change approval semantics.

Each operation contains `x-harness-requirement-refs` with approved acceptance-
criterion and business-rule IDs. Metadata traceability is derived from these
extensions and must match them exactly.

## UX And Gates

Show method, path, purpose, authentication, success and failure responses, and
feature links before developer details. Ask about only material unresolved API
behavior. Keep hashes internal.

A draft may be saved with semantic blockers. Approval requires all acceptance
criteria and business rules to be covered, valid success and failure responses,
matching path parameters, valid security references, and compatibility with the
technology profile. Authorized operations describe both 401 and 403. Session
uses a cookie security scheme, token uses HTTP bearer, OIDC uses OpenID Connect
or OAuth2, and `security.none` must not secure operations.

Approval revalidates the approved route and its inputs, checks the exact OpenAPI
and metadata shown to the user, keeps OpenAPI unchanged, and atomically updates
metadata and its Markdown view. Contract approval permits implementation
planning only; it does not authorize source changes.
