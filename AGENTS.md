# AGENTS.md

This repository is an evidence-first harness for creating and growing external
Spring projects. The target may be an empty repository, a small application, or
a large multi-stage system. The user should be able to work in natural language
without typing commands.

The Harness has one mode: `start`. Read `modes/start.md` before acting. Use the
`spring-project-start` skill for creating a project, continuing it, or adding
the next planned capability.

## Routing

Resolve the target and run preflight instead of asking the user to classify the
project.

```text
scripts/check-target --target <target-path>

  SPRING_PROJECT: no       → initialize the project from its README or agreed scope
  SPRING_PROJECT: yes      → read progress and project evidence, then continue building
  SPRING_PROJECT: UNKNOWN  → report UNKNOWN and ask one short question only if needed
```

An existing Spring layout does not select another mode. It means the project has
already started and the next planned milestone should continue from current
evidence.

## Non-Negotiable Rules

- The target repository is external. Never create target source inside this
  Harness repository, and never use `workspace/target-solution`.
- All target commands must use the target repository root as the explicit
  working directory.
- Do not mix Harness Git state with target Git state.
- Confirm target preflight before editing: `TARGET_EXISTS`,
  `TARGET_IS_DIRECTORY`, `TARGET_IS_GIT_REPOSITORY`,
  `TARGET_IS_HARNESS_REPO: no`, `TARGET_GIT_ROOT`, and `TARGET_BRANCH`.
- Protect existing dirty changes. Do not overwrite files you did not change.
- If evidence is missing, or a script fails, report `UNKNOWN`. Do not infer the
  missing result.
- Do not store passwords, tokens, API keys, credentials, PII, production
  customer data, full production logs, or secret-bearing config in this
  repository or in anything it generates.
- Do not modify `/root/project-analysis-harness`.

## Project Scale

Project size is not limited. Keep the whole product direction visible while
implementing one coherent, verifiable milestone at a time.

- Small projects may move directly from setup to a first feature.
- Large projects first need an explicit scope, staged roadmap, module boundaries,
  and verification strategy appropriate to their requirements.
- Add infrastructure, security, persistence, messaging, deployment, or module
  separation when requirements or the current stage justify them; do not add
  them merely because the eventual project may be large.
- A milestone may span multiple files and layers. "One milestone" does not mean
  "one trivial code edit."

## Scripts

These are agent tools. The user never needs to run them. Always pass the target
root explicitly.

```bash
scripts/check-environment
scripts/check-target --target <target-path>
scripts/check-spring-project --target <target-path>
scripts/run-verification --target <target-path>
```

Run `check-environment` before the first session of a project. If no `--target`
is given, scripts fall back to `target.repository` in the git-ignored
`config/target.local.yaml`.

Run `tests/run-tests` after changing anything under `scripts/`.

## Git Safety

Before editing a target repository, run target preflight and check target Git
status. Check Harness Git status separately when changing Harness files. Never
run destructive Git commands unless the user explicitly asks.

Destructive commands include:

```text
git reset --hard
git clean -fd
git restore .
git checkout .
git push --force
git branch -D
```

## Evidence And UNKNOWN

Use actual files, tests, runtime output, Git state, and user-approved
requirements as evidence. Trust evidence in this order:

```text
Actual files
Tests
Runtime output
Git state
README and project documents
User-approved requirements
AI inference
```

Scripts use these exit codes:

```text
0  confirmed
1  confirmed negative or tests failed
2  usage error or unsafe condition
3  cannot verify (UNKNOWN)
```

Exit code 3 is not a confirmed failure. Report it as `UNKNOWN` with the reason.
