# Compatibility Rules

Review the complete selected profile before implementation. These rules are
guardrails, not an exhaustive compatibility database. Current framework and
vendor support must be verified from authoritative documentation when exact
versions matter.

## Result Levels

| Result | Action |
|---|---|
| `SUPPORTED` | Proceed and record important implications |
| `REVIEW_REQUIRED` | Explain cost or missing design and request a decision |
| `CONFLICT` | Do not generate the conflicting structure until resolved |

## Cross-Decision Rules

### Interface and Packaging

- API-only plus a server view engine: `REVIEW_REQUIRED` unless both channels
  are intentional.
- JSP plus executable packaging or embedded-container assumptions:
  `REVIEW_REQUIRED`; verify the selected Spring Boot/container deployment model.
- Separate SPA plus server session authentication: `SUPPORTED` only after
  origin, cookie, CSRF, and deployment boundaries are defined; otherwise
  `REVIEW_REQUIRED`.

### Security

- `NOT_USED` security plus user-specific authorization: `CONFLICT`.
- JWT chosen only because the application exposes REST: `REVIEW_REQUIRED`.
- Session authentication across independently deployed services:
  `REVIEW_REQUIRED`; define shared session or gateway behavior.
- External identity provider without issuer, client type, or trust boundary:
  `UNKNOWN` and blocking when authentication is in the current milestone.

### Data

- Multiple data sources without ownership and routing rules:
  `REVIEW_REQUIRED`.
- One local atomic transaction across independent databases or services:
  `CONFLICT` unless a verified transaction mechanism is deliberately selected.
- JPA, MyBatis, and JDBC together: `SUPPORTED` when responsibilities are
  explicit; otherwise `REVIEW_REQUIRED`.
- Database-per-service plus direct cross-service table access: `CONFLICT` with
  service ownership.
- Production relational database without a schema migration owner or process:
  `REVIEW_REQUIRED`.

### Architecture and Operations

- MSA without independent deployment or ownership needs: `REVIEW_REQUIRED` due
  to operational cost.
- MSA with one shared database: `REVIEW_REQUIRED`; define ownership and coupling.
- Kubernetes selected without a deployment requirement: `REVIEW_REQUIRED`.
- Messaging without retry, duplicate, ordering, and failure expectations:
  `REVIEW_REQUIRED` before implementing business-critical consumers.

### Verification

- Multiple databases without integration verification: `REVIEW_REQUIRED`.
- MSA without service integration or contract verification: `REVIEW_REQUIRED`.
- Security in scope without authentication and authorization tests:
  `REVIEW_REQUIRED`.
- Migration tooling in scope without migration verification:
  `REVIEW_REQUIRED`.

## Custom Input

For a custom technology or topology:

1. preserve the user's terminology;
2. map it to affected decision axes;
3. identify version-sensitive claims as `UNKNOWN` until verified;
4. apply applicable cross-decision rules;
5. add a project-specific compatibility note rather than silently forcing it
   into the nearest preset.
