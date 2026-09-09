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

## Contract Preparation Handoff

After an HTTP API route decision has a committed application receipt and the
latest route revision is approved, create one immutable handoff per active
`contractId`. Revalidate the receipt, decision approval, route journal,
revision ancestry, feature, project brief, technology profile, discovery, and
evidence. An earlier contract decision may point to an intermediate revision;
the final approved route is acceptable only when every immutable `previous`
reference proves that it is a descendant.

The handoff selects the disposition adapter and proposed output paths without
executing it. For existing APIs, freeze the selected operation IDs, methods,
paths, requirement references, complete inline operation documents, path
parameters, effective security, reachable local components, and unresolved
external references into a normalized snapshot hash. Missing coverage,
external references, or occupied outputs produce a visible `BLOCKED` handoff.
Validate the exact handoff again immediately before a later adapter consumes
it. Handoff preparation never creates contract artifacts, edits OpenAPI, or
changes source.

## Existing APIs

Before choosing an existing API, run bounded read-only discovery with
`discover_http_api_evidence.py` and revalidate its report/view with
`validate_http_api_evidence_discovery.py`. Discovery prefers semantically valid
OpenAPI JSON, separates observed operations from feature-term matches, and
requires matching-operation traceability plus no semantic blockers before
recommending `REUSE`. Related incomplete contracts may be `EXTEND` candidates.
Controllers are supporting evidence only, dirty files are `UNSTABLE`, YAML is
`UNSUPPORTED`, and a truncated scan is `UNKNOWN`. Discovery itself never edits
the design route. Hash and parse the same single-read byte snapshot; a file that
changes during that read is unstable. Preserve malformed or unreadable possible
contract evidence as `UNKNOWN` instead of treating it as absent. More than one
contract candidate also requires an explicit choice. The user view identifies
each candidate and shows its path, matched operations, requirement coverage,
decision reasons, and remaining ambiguity.

`REUSE` and `EXTEND` require an existing OpenAPI JSON file recorded in route
code evidence. `REUSE` points to that exact file and never copies or edits it.
`EXTEND` writes a separate proposed OpenAPI and compares it with the baseline;
approval still does not apply the proposal to the existing interface.

Metadata selects only the operation IDs used by the current feature. Validation,
traceability, Controller evidence, and the basic user view apply to that subset;
unrelated operations in a large service contract are not forced into the
feature. REUSE external-reference checks follow only the selected operations and
their reachable local components. An EXTEND compatibility report still protects
the complete proposed change.

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
required request body, removed request or response media types, and removed or
changed response headers. Component-level request bodies, responses, parameters,
headers, and schemas are resolved through local JSON Pointer references. When baseline evidence is stale, malformed, outside the
target, or otherwise unreadable, rendering still produces a safe recovery view
with the current state and three next actions. It does not expose internal paths
or raw errors in the basic view.

Prepare a v2 handoff only after the selected operation IDs are explicitly
confirmed. The safe default ownership policy is exclusive: a baseline already
owned by another active HTTP API contract is not shared, even when proposed
operation subsets appear disjoint. This avoids ambiguous future component and
security ownership. External `$ref` values are never fetched implicitly and
block apply until a separately immutable evidence workflow is available.

Run `prepare_http_api_contract_dry_run.py` to bind the exact proposal source
(EXTEND) or baseline snapshot (REUSE), derive metadata and compatibility bytes,
and report output collisions without writing them. `REVIEW`, `BREAKING`,
`SECURITY`, and `UNKNOWN` compatibility findings keep the report blocked.
Record a clear report with `record_http_api_contract_dry_run_approval.py`, then
use `apply_approved_http_api_contract.py`. It re-renders and compares every
planned SHA-256 immediately before a create-only transaction. It records a
PREPARED/APPLYING/COMMITTED journal and committed baseline; exact partial files
are rolled back automatically. Use `recover_http_api_contract_apply.py` only
after process interruption. Legacy direct materializers are intentionally
disabled so they cannot bypass handoff, dry-run, or approval.

After apply, validate with `validate_existing_http_api_contract.py`, render with
`render_existing_http_api_contract.py`, and use
`record_existing_http_api_contract_approval.py` for the later semantic contract
approval. Contract materialization approval and semantic contract approval are
separate decisions.
