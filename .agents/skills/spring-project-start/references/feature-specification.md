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
6. Record explicit approval and the displayed `approval-content-sha256` only
   after showing that exact summary. Regenerate the Markdown after recording
   approval. Project-brief approval does not approve a feature, and feature
   approval does not approve later file application.

## Files

- `<target>/docs/project-brief.json`: project goal and ordered feature map.
- `<target>/docs/project-brief.md`: generated user view.
- `<target>/docs/features/F001/spec.json`: one feature contract.
- `<target>/docs/features/F001/spec.md`: generated user view.

Use stable IDs: `F001`, `BR-F001-01`, `AC-F001-01`, and `U-F001-01`.
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
```

Use `--check` to detect a stale Markdown view. Do not overwrite an existing
view without `--force` unless the user approved regenerating that derived file.
