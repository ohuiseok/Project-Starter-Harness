# HTTP API Contracts

Use this workflow only for an approved route v2 instance whose kind is
`HTTP_API`. Every active v2 instance has an `artifactPath` for its metadata.

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

## Existing APIs

`REUSE` and `EXTEND` require an existing OpenAPI JSON file recorded in route
code evidence. `REUSE` points to that exact file and never copies or edits it.
`EXTEND` writes a separate proposed OpenAPI and compares it with the baseline;
approval still does not apply the proposal to the existing interface.

Metadata selects only the operation IDs used by the current feature. Validation,
traceability, Controller evidence, and the basic user view apply to that subset;
unrelated operations in a large service contract are not forced into the
feature. The compatibility report still protects the complete proposed change.

Local JSON Pointer `$ref` values are resolved recursively before schema
comparison, including component changes and cycles. External references are
`UNKNOWN` until their immutable content is supplied as evidence.

The compatibility report treats removed operations or responses, changed path
or method, newly required parameters or authentication, incompatible schema
types, removed properties or enum values, and newly required request fields as
breaking. Breaking changes cannot be approved as an in-place extension. Other
schema differences are `REVIEW`. Every review has a structured decision with
status, reason, source, and user-confirmation flag. An accepted review without a
resolved reason and explicit user confirmation remains blocked; a general
approval does not silently accept it. Authentication removal or weakening is a
non-waivable security blocker in this workflow.

The basic view shows selected operations only, expands feature IDs into their
approved descriptions, and explains each difference with before/after values,
impact, recommendation, accepted risks, and next actions.

Legacy metadata with `acceptedCompatibilityReviews` has neither a selected
operation boundary nor a recorded acceptance reason. Migrate it to a separate
file with `migrate_existing_http_api_contract_v2.py`. The migration never
inherits approval and returns every review to `PENDING` for explicit review.

When route evidence includes files with kind `SPRING_CONTROLLER`, the harness
joins literal class- and method-level Spring mapping paths and requires exact
method/path equality with selected baseline operations. Literal arrays and
standard Java or Kotlin mapping annotations are supported. Constants, custom
composed annotations, or mappings without a literal HTTP method are `UNKNOWN`;
substring path matches are never proof.

Compatibility assessment also protects removed or changed parameters, a newly
required request body, removed request or response media types, and removed
response headers. When baseline evidence is stale, malformed, outside the
target, or otherwise unreadable, rendering still produces a safe recovery view
with the current state and three next actions. It does not expose internal paths
or raw errors in the basic view.

Create the evidence assessment with `create_existing_http_api_contract.py`,
validate it with `validate_existing_http_api_contract.py`, and render it with
`render_existing_http_api_contract.py`. After explicit approval use
`record_existing_http_api_contract_approval.py`, which rechecks the route,
baseline, proposal, comparison report, and Markdown atomically.
