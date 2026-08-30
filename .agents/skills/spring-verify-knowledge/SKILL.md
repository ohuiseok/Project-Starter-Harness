---
name: spring-verify-knowledge
description: Use for Spring/Spring Boot/MyBatis/JPA diff review, verification, Git pull impact analysis, stale knowledge candidate detection, and knowledge proposal. Do not overwrite Knowledge automatically.
---

# Spring Verify Knowledge

Use this skill when the user asks to review changes, run verification, inspect
Git pull impact, detect stale Knowledge, or propose long-term Knowledge updates.
Also use it to review Level 2 auto-check reports under
`reports/auto-check/unreviewed/` or `reports/auto-check/latest.md`.

## Rules

Follow `AGENTS.md` for the shared rules and `modes/maintain.md` for this mode:
the approval model, evidence separation, customer safety, minimal change and
the auto-check rules. Do not restate them here.

## Workflow

1. Resolve and preflight the target repository.
2. Review the target diff from the target repository root.
3. If an unreviewed auto-check report exists, read it and reflect related
   changes in the current task context by re-checking target code evidence.
4. Run deterministic scripts as needed:
   `detect-changes`, `stale-candidates`, and context helpers.
5. Run available build or test commands only when appropriate.
6. Produce a verification report using `templates/verification-report.md`.
7. Propose Knowledge changes using `templates/knowledge-proposal.md`.
8. Leave Knowledge update to human approval.

## Safety

Script failure means `UNKNOWN`; do not fill gaps with inference.
Auto-check recommendation is a rule-based candidate, not fact.
