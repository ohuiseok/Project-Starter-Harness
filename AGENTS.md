# AGENTS.md

This repository is a Project Starter Harness for helping beginner developers
create and learn small Spring Boot projects with GPT/Codex.

This file is the single source of truth for how the agent must behave. The
files under `docs/` explain the same workflow to humans and must not restate
these rules — they link here instead.

## Non-Negotiable Rules

- Ask one question at a time.
- Keep questions short.
- Offer 2 to 4 choices.
- Every choice set must include a recommended option.
- If the user does not know, continue with the recommended option.
- Work on one small session goal at a time.
- Explain briefly while implementing, using beginner-friendly language.
- Verify with a test or run check before ending a session.
- End every session with a short summary and next-step choices.
- Do not include heavy defaults unless the user asks for them.
- Protect existing dirty changes.
- Keep target repository Git state separate from Harness Git state.
- The target Spring repository is external. Do not create target source inside
  this Harness repository.
- All target commands must use the target repository root as the explicit
  working directory.
- Do not modify `/root/project-analysis-harness`; it is reference-only.
- If evidence is missing, report `UNKNOWN` instead of guessing.

## Beginner UX

The user may say only:

```text
시작해줘
추천으로 해줘
이어가자
```

Treat these as valid instructions. Read the target repo first, summarize what is
confirmed, then ask the next short question.

## Session Shape

Use this flow:

```text
Preflight
README summary
One short question
One small session goal
Implementation
Verification
Summary
Next-step choices
```

Before implementation, confirm the current session goal briefly.

## Technical Defaults

Recommend this stack unless the target README says otherwise:

- Java 17
- Spring Boot
- Gradle
- Spring Web
- Spring Data JPA
- H2
- JUnit
- static `index.html`

Exclude by default:

- login
- Spring Security
- PDF upload
- OCR
- RAG
- automated recommendation or judgment
- Docker
- MySQL
- React/Vue
- MSA, Kafka, Kubernetes
- forced Clean Architecture

The recommended MVP shape is: first page, then create, then list, then detail,
for one domain object. Concrete per-project MVPs live in `examples/`.

## Scripts

These are agent tools. The user never runs them and the README does not show
them. Always pass the target root explicitly.

```bash
scripts/check-target --target <target-path>          # preflight
scripts/check-spring-project --target <target-path>  # layout details
scripts/run-verification --target <target-path>      # tests
```

`tests/run-tests` covers the scripts themselves. Run it after changing anything
under `scripts/`.

## Git Safety

Before editing a target repo:

- Run target preflight.
- Check target Git status.
- Check Harness Git status separately when changing Harness files.
- Do not overwrite dirty files you did not change.
- Never run destructive Git commands unless the user explicitly asks.

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

Use actual files, scripts, test output, runtime output, and Git state as
evidence. Trust evidence in this order:

```text
Actual files
Tests
Runtime output
Git state
README
User approval
AI inference
```

If something cannot be confirmed, say `UNKNOWN`.

Scripts follow the same convention through their exit codes:

```text
0  confirmed
1  confirmed negative (target missing, tests failed)
2  usage error
3  cannot verify (UNKNOWN)
```

Exit code 3 means the check could not run. It is not a failure and must be
reported as `UNKNOWN`.
