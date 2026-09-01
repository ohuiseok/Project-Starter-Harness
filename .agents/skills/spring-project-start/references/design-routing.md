# Design Routing

Use design routing after the feature specification and technology profile are
approved, and before creating API, data, UI, messaging, integration, security,
or verification contracts. The route chooses artifacts; it does not contain
their detailed design.

## Inputs

- the approved feature schema v2 and exact file SHA-256;
- the approved project brief and exact file SHA-256;
- the confirmed technology profile and exact file SHA-256;
- only code files that prove an `EXTEND` or `REUSE` decision, with target-
  relative paths and hashes.

Never claim reuse from a README or inference when actual code evidence can be
checked. A changed input or evidence file makes the route stale.

## Dispositions

- `CREATE`: create a new contract at `artifactPath`;
- `EXTEND`: change an existing design proved by `evidencePaths`;
- `REUSE`: use existing behavior proved by `evidencePaths`;
- `NOT_NEEDED`: the approved feature explicitly does not need it;
- `DEFERRED`: the approved feature defers it;
- `UNKNOWN`: the target or action is not yet known and blocks advancement.

Every active route names a technology-profile project ID and a module path.
Persistence in a multi-store profile also names the applicable data-store IDs.
Do not duplicate API fields, entities, table columns, or screen details in the
route; those belong to later contracts.

## Conversation

Show three short groups: what will be created or reused, what must be confirmed
now, and what is deferred. Ask only about a material `CREATE / EXTEND / REUSE`
choice or target that evidence cannot resolve. Keep internal hashes hidden.
One confirmation can approve the displayed route, but it does not approve code
application.

The basic Markdown view must use the same assessment as the readiness gate,
including profile and target-evidence checks. Show every blocker in user
language and distinguish `drafting`, `decision required`, `input changed`,
`waiting for approval`, and `approved`. Internal IDs and raw blocker codes stay
in the full developer view.

## Gates

Validate current inputs and target evidence:

```bash
python3 .agents/skills/spring-project-start/scripts/validate_design_route.py \
  --route <target>/docs/features/<feature-id>/design-route.json \
  --feature <target>/docs/features/<feature-id>/spec.json \
  --project-brief <target>/docs/project-brief.json \
  --profile <target>/docs/project-profile.json \
  --target <target> --require-ready
```

Advancement requires an approved feature, ready technology profile, approved
route, current input hashes, current code evidence, resolved dispositions,
valid project/store references, and confirmation of AI-proposed routing.

## Design References

- [GitHub Spec Kit implementation workflow](https://github.com/github/spec-kit/blob/main/templates/commands/implement.md)
  separates plan, optional contracts/data model, tasks, and implementation.
- [Backstage descriptor format](https://github.com/backstage/backstage/blob/master/docs/features/software-catalog/descriptor-format.md)
  uses stable component, API, resource, and dependency references.
- [Backstage entity-reference ADR](https://github.com/backstage/backstage/blob/master/docs/architecture-decisions/adr009-entity-references.md)
  motivates explicit, stable target identities instead of display names.
