# AGENTS.md

This repository is a Project Starter Harness for helping beginner developers
create and learn small Spring Boot projects with GPT/Codex.

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

## Recommended P0 MVP For Verasure

Use this recommendation for `/tmp/Verasure` unless the target README says
otherwise:

- Java 17
- Spring Boot
- Gradle
- Spring Web
- Spring Data JPA
- H2
- JUnit
- static `index.html`
- insurance information create
- insurance information list
- insurance information detail
- status display: `CONFIRMED`, `UNKNOWN`, `NEEDS_REVIEW`

Exclude by default:

- login
- PDF upload
- OCR
- RAG
- insurance recommendation or judgment
- Spring Security
- Docker
- MySQL
- MSA, Kafka, Kubernetes
- forced Clean Architecture

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
evidence.

If something cannot be confirmed, say `UNKNOWN`.

