---
name: spring-project-start
description: 빈 repo, README-only repo, 또는 이미 시작된 Spring 프로젝트에서 규모와 관계없이 프로젝트를 만들고 계속 확장할 때 사용합니다. 사용자가 "시작해줘", "추천으로 해줘", "이어가자", "다음 기능을 만들자"라고 말해도 이 Skill을 씁니다.
---

# spring-project-start

Use this Skill to create or continue an external Spring project. The project may
be a small application or a large system developed through multiple milestones.

## Rules

Follow `AGENTS.md` and `modes/start.md`. Project size is unlimited, but each
session should deliver one coherent milestone that can be verified.

## Required Behavior

1. Resolve the external target repository.
2. On the first session, run `scripts/check-environment`.
3. Run `scripts/check-target --target <target-path>`.
4. If a Spring layout exists, run
   `scripts/check-spring-project --target <target-path>`.
5. Read target instructions, `docs/progress.md`, README, build files, and only
   the source needed to understand the current milestone.
6. Protect existing dirty changes and keep Harness and target Git state separate.
7. Determine whether this is initialization or continuation; do not route to a
   different mode merely because Spring source already exists.
8. Summarize the current project goal, evidence, and UNKNOWN briefly.
9. Create or confirm the project brief and feature candidates using the Feature
   Specification workflow below.
10. For a large or underspecified project, establish a staged roadmap before
   implementation. Record architecture and operational choices only to the
   depth needed for the current and near-term stages.
11. Select the next vertical slice and identify only its relevant design needs.
12. Create or confirm the technology profile using the Technology Selection
    workflow below.
13. Complete and approve the selected feature specification.
14. Read `references/design-routing.md`, create and approve the design route,
    then create only the contracts selected by that route.
15. Confirm one coherent, verifiable milestone and implement it.
16. Add only technology justified by requirements or the current stage.
17. Verify with tests or a run check.
18. Update `<target>/docs/progress.md` and close with the session summary.

## Feature Specification

For a new product goal, a missing brief, or the next feature, read
`references/feature-specification.md` completely. Create
`<target>/docs/project-brief.json` and one feature contract under
`<target>/docs/features/<feature-id>/spec.json`. For the first feature use
`F001`; on continuation resolve the next unused stable ID from both the project
brief and existing feature directories with `scripts/next_feature_id.py`.
Generate their Markdown views; never ask the user to author JSON.
Feature contracts use schema v2 design requirements. If a target contains a v1
contract, migrate it to a separate file with `migrate_feature_spec_v2.py`, show
the unresolved interpretations, and replace the original only after review.

Show the understood goal, users, feature candidates, recommended next slice,
blocking questions, and deferrable questions. Preserve whether each important
decision came from the user, project evidence, a recommendation, an inference,
or remains unknown. Ask one material question at a time and keep API, database,
messaging, scheduled work, and UI optional.

Validate before API/data design or implementation:

```bash
python3 .agents/skills/spring-project-start/scripts/validate_feature_specs.py \
  --project-brief <target>/docs/project-brief.json \
  --feature <target>/docs/features/<feature-id>/spec.json --require-approved

python3 .agents/skills/spring-project-start/scripts/render_spec_markdown.py \
  --input <target>/docs/features/<feature-id>/spec.json \
  --project-brief <target>/docs/project-brief.json \
  --output <target>/docs/features/<feature-id>/spec.md --check
```

Treat `SPEC_VALID` and `ADVANCEMENT_READY` separately. A valid draft may be
saved, but do not design APIs, data models, or implementation tasks while a
blocking unknown, unconfirmed AI-proposed rule, incomplete acceptance criterion,
unknown or unconfirmed design requirement, missing project feature ID, missing
approval, or stale Markdown view remains.
Keep content hashes internal. After the user approves the displayed summary,
use `record_spec_approval.py` to atomically record project and feature approvals,
synchronize the candidate status, and regenerate both Markdown views; never ask
the user to copy or verify a hash. One user response may approve both summaries,
but store two independent approvals. Regenerate derived Markdown automatically
after an approved JSON change when no independent edit would be overwritten.

## Design Routing

After feature and technology approval, route the current slice with
`templates/design-route.json`. Record it at
`<target>/docs/features/<feature-id>/design-route.json` and generate the sibling
Markdown view. Use actual target files as evidence for `EXTEND` and `REUSE`.
Active routes must reference technology-profile project IDs and, for complex
persistence, data-store IDs. Do not put detailed API fields, entities, or UI
design in this manifest.

Validate current inputs and evidence with `validate_design_route.py`. After the
user confirms the displayed summary, use `record_design_route_approval.py`; it
rechecks the route, feature, profile, code evidence, and Markdown before safely
updating the JSON and view. `DESIGN_READY: yes` permits contract design, not
source-file application.
Render the basic route view with the same target-aware assessment used by the
validator. Never hide a readiness blocker only in detailed or command output.

Route schema v2 gives every routed artifact a stable `contractId` and permits
multiple instances of the same kind for multi-module and distributed features.
Do not add detailed interface fields to the route. Migrate a v1 route to a
separate v2 file with `migrate_design_route_v2.py`; the migrated copy requires
review and approval.

Create selected detailed contracts from `templates/design-contract.json`.
The metadata owns target identity, route linkage, evidence, traceability, and
approval only. A standard artifact such as OpenAPI owns its interface details;
never duplicate request or response schemas in metadata. Validate metadata with
`validate_design_contract.py` and render its user view with
`render_design_contract.py`. A ready contract permits implementation planning,
not source-file application.

For a route v2 `HTTP_API` instance with disposition `CREATE`, read
`references/http-api-contracts.md` completely. Materialize an agent-prepared
OpenAPI JSON draft and derived metadata with `create_http_api_contract.py`,
validate them with `validate_http_api_contract.py`, and render the basic view
with `render_http_api_contract.py`. After the user approves that view, use
`record_http_api_contract_approval.py`; it rechecks current route inputs and the
exact OpenAPI without modifying the OpenAPI artifact. Do not use this CREATE
workflow for `EXTEND` or `REUSE`. For those dispositions follow the Existing
APIs section of `references/http-api-contracts.md`; require baseline OpenAPI
evidence, generate a deterministic compatibility report, and never apply the
proposed extension during contract approval.

## Technology Selection

For a new project, a missing profile, or a requested stack change, read
`references/technology-decisions.md` and
`references/compatibility-rules.md` completely before asking stack questions.
Load the structured choices from `references/technology-options.json`, reusable
recommendations from `references/profiles.json`, and deterministic combination
rules from `references/compatibility-rules.json`. The JSON catalogs are the
machine-readable source for IDs and predefined combinations; the Markdown files
explain the interaction and judgment around them.

Before using a changed catalog, run:

```bash
python3 .agents/skills/spring-project-start/scripts/validate_catalog.py
```

Evaluate a populated structured profile with:

```bash
python3 .agents/skills/spring-project-start/scripts/evaluate_profile.py \
  --profile <target>/docs/project-profile.json
```

Before generation, require the readiness gate:

```bash
python3 .agents/skills/spring-project-start/scripts/evaluate_profile.py \
  --profile <target>/docs/project-profile.json --require-ready
```

Treat `PROFILE_VALID`, `COMPATIBILITY_RESULT`, and `GENERATION_READY` as
different results. Never interpret `SUPPORTED` alone as permission to generate.

1. Infer a recommended profile from the user's product description and known
   constraints. Start from a catalog profile only when its `useWhen` matches;
   otherwise compose a custom profile. Never infer an unstated mandatory
   constraint.
2. Show the compact recommendation first, with three actions:
   accept the recommendation, edit it one decision at a time, or describe a
   custom stack in free text.
3. When asking about one decision, offer 2 to 4 relevant representative choices
   plus `Other / direct input`. Mark one recommendation and explain its impact
   in one short sentence. Do not show irrelevant choices.
4. Treat custom input as a first-class answer. Normalize it into one or more
   decisions, summarize the interpretation, and ask one follow-up only when an
   ambiguity changes implementation materially.
5. Mark every decision as `NOW`, `SOON`, `DEFERRED`, `NOT_USED`, or `UNKNOWN`.
   Do not force decisions that can safely be deferred.
6. Run the compatibility review before confirmation. Report `SUPPORTED`,
   `REVIEW_REQUIRED`, or `CONFLICT`, including cost or consequence. Apply both
   the structured rules and relevant judgment rules from the Markdown reference.
7. Show the final profile and obtain confirmation before generating project
   structure or dependencies. Write structured decisions to
   `<target>/docs/project-profile.json` using `templates/project-profile.json`;
   write the user-readable rationale to `<target>/docs/project-profile.md`
   using `templates/project-profile.md`. Keep both synchronized, with JSON as
   the machine-readable selection source.
8. Run profile evaluation after confirmation. Do not create project files or
   dependencies unless `GENERATION_READY: yes`. Show every blocker and return to
   only the affected decision.
9. After readiness passes, compile `<target>/docs/generation-plan.json` using
   current Spring Initializr metadata. This step may write the plan only; it
   must not generate or modify target source files.
10. Validate the plan and show its Initializr request, project shape,
    contributors, prerequisites, secret names, reviews, and verification intent.
    Keep `executionReady: false` until a later dry run and user approval.
11. When continuing an existing project, prefer actual build and configuration
    evidence. Do not replace observed technology merely because a different
    default would be recommended.

## Safe Dry Run

After a plan is `READY_FOR_DRY_RUN`, render the Initializr archive only in a
temporary directory and compare it with the external target:

```bash
python3 .agents/skills/spring-project-start/scripts/render_generation_dry_run.py \
  --plan <target>/docs/generation-plan.json \
  --target <target> \
  --output <target>/docs/generation-dry-run.json
```

The dry run must not write source files. A missing target file is `CREATE`.
Different content is `UPDATE` only when its current SHA-256 matches an approved
baseline manifest; otherwise it is `CONFLICT`. Symlinks, path-type collisions,
unresolved reviews, multi-project plans without child plans, and contributors
without deterministic renderers also conflict. Never treat a clear dry run as
approval: keep `executionReady: false` until the user reviews the report and
explicitly approves a later apply milestone.

For deterministic tests or offline evidence, `--rendered-source` or
`--rendered-archive` may replace the live Initializr download. These inputs are
read-only and do not relax comparison rules. Do not use `--force` to replace a
report unless that replacement is in the approved milestone.

## Approved Apply

After the user reviews a conflict-free report, record explicit approval with
the exact report SHA-256 using `templates/generation-approval.json`. Then apply
the same rendered result:

```bash
python3 .agents/skills/spring-project-start/scripts/apply_approved_generation.py \
  --plan <target>/docs/generation-plan.json \
  --report <target>/docs/generation-dry-run.json \
  --approval <approval.json> \
  --target <target>
```

Apply only when the approval hash and canonical target match. Re-render and
match every desired hash and mode, then recheck every target path immediately
before writing. Back up replaced files, the approval, the report, and any prior
baseline under `<target>/.starter-harness/backups/`. Stage replacements on the
target filesystem, use atomic file replacement, and roll back every applied
file if a commit step fails. On success, write
`<target>/.starter-harness-generation.json` last. Never manufacture approval
from an earlier general instruction; approval must follow the displayed dry-run
report for that exact target and hash.

## Generation Planning

Use `references/generation-mappings.json` to translate selected option IDs into
Spring Initializr dependency IDs and generator contributor intents. Obtain
current metadata from the official `https://start.spring.io/metadata/client`
endpoint and save it as a temporary evidence file; do not hardcode current
Spring Boot versions.

Compile and validate without changing target source:

```bash
python3 .agents/skills/spring-project-start/scripts/compile_generation_plan.py \
  --profile <target>/docs/project-profile.json \
  --metadata <metadata.json> \
  --output <target>/docs/generation-plan.json

python3 .agents/skills/spring-project-start/scripts/validate_generation_plan.py \
  --plan <target>/docs/generation-plan.json
```

Do not use `--force` unless replacing an existing generation plan is within the
current approved milestone. A compiled plan is ready only for a future dry run,
not for file application. Resolve `REVIEW_REQUIRED` plan items before making a
dry run executable.

## Milestone Sizing

A milestone may cross controller, service, persistence, configuration, and test
layers when they form one usable capability. Avoid both extremes:

- do not attempt the complete large system in one session;
- do not split work into edits too small to demonstrate useful behavior.

Examples:

- project skeleton plus health check and build verification;
- customer registration API with persistence and tests;
- authentication foundation for one approved user flow;
- first module boundary and an end-to-end vertical slice;
- deployment-ready packaging for the current application stage.

## Technology Changes

Prefer the simplest option that satisfies approved requirements. Security,
production databases, migrations, messaging, caching, batch, containers,
frontend frameworks, multi-module builds, and distributed architecture are
available when justified; they are neither mandatory defaults nor blanket
exclusions.

Re-open only the affected decision and its compatibility dependents when the
user changes the stack. Preserve the reason and previous decision in the target
project's normal Git history rather than maintaining a separate history here.

## Verification

Run:

```bash
scripts/run-verification --target <target-path>
```

Exit code 3 means verification could not run. Report `UNKNOWN` and the reason.
Do not hide test failures.

## Session Ending

Keep `<target>/docs/progress.md` useful for the next session. Report:

```text
완료:
- ...

중요한 결정:
- ...

실행/테스트:
- ...

남은 UNKNOWN:
- ...

다음:
1. 추천: ...
2. ...
3. ...
```
