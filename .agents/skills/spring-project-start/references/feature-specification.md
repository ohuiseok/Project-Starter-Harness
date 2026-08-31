# Feature Specification

Use this workflow after the product goal is known and before designing APIs,
data models, or implementation files. JSON is the machine-readable source;
Markdown is a generated view for the user.

## Conversation

1. Summarize the understood goal, users, success criteria, non-functional
   requirements, scope, and feature candidates before asking questions.
2. Distinguish `USER_STATED`, `PROJECT_EVIDENCE`, `RECOMMENDED`, `INFERRED`,
   and `UNKNOWN`. Never present a recommendation or inference as a user fact.
3. Show the recommended first vertical slice. Offer `accept recommendation`,
   `edit one item`, and `direct input`.
4. Ask only about unresolved decisions that materially change the feature.
   Ask one question at a time with 2–4 relevant choices and
   `Other / direct input`. Allow `use recommendations for the rest`,
   `change an earlier answer`, and `defer`.
5. Present a feature summary in user language: user value, flow, rules,
   authorization, state, failures, acceptance criteria, design needs, and
   remaining unknowns.
6. Show stage progress as `goal and users → feature choice → rules and access →
   final review`; do not predict a fixed number of questions.
7. After the user approves the displayed summary, compute and store its content
   hash internally. Never show or ask the user to handle the hash. A single user
   response may approve the project brief and first feature, but record each
   approval independently. Feature approval does not approve file application.

## Files

- `<target>/docs/project-brief.json`: project goal and ordered feature map.
- `<target>/docs/project-brief.md`: generated user view.
- `<target>/docs/features/F001/spec.json`: one feature contract.
- `<target>/docs/features/F001/spec.md`: generated user view.

Use stable IDs: `F001`, `BR-F001-01`, `AC-F001-01`, and `U-F001-01`.
Give every feature candidate a short `recommendationReason`, `dependsOn`, and
`blockingUnknownIds`. Recommend only a non-deferred candidate whose dependencies
are verified and whose linked unknowns are resolved. Explain the reason in user
language.
Do not require an HTTP API or relational data. Entry and effect needs are
booleans under `designNeeds`, so REST, server-rendered UI, batch, scheduled,
messaging, and integration features use the same contract.

## Gates

Allow incomplete documents to remain valid `DRAFT` or `REVIEW_REQUIRED`
artifacts. Block advancement when:

- approval is absent or incomplete;
- a blocking unknown remains unresolved;
- user value, main flow, business rules, or acceptance criteria are missing;
- an inferred or recommended mandatory rule has not been confirmed by the user;
- the feature ID is absent from the project brief;
- JSON and its generated Markdown view differ.

Run:

```bash
python3 .agents/skills/spring-project-start/scripts/validate_feature_specs.py \
  --project-brief <target>/docs/project-brief.json

python3 .agents/skills/spring-project-start/scripts/validate_feature_specs.py \
  --feature <target>/docs/features/F001/spec.json \
  --project-brief <target>/docs/project-brief.json --require-approved

python3 .agents/skills/spring-project-start/scripts/render_spec_markdown.py \
  --input <json> --output <markdown>

python3 .agents/skills/spring-project-start/scripts/record_spec_approval.py \
  --project-brief <project-json> --feature <feature-json> \
  --expected-project-hash <internal-hash> \
  --expected-feature-hash <internal-hash> \
  --approved-by <user> --approved-at <ISO-8601>
```

Use `--check` to detect a stale Markdown view. Use the default basic view for
users and `--detail full` only on request. Regenerate a derived view after an
intentional JSON change without asking for another approval; first ensure the
view has no independent edits that would be lost.
