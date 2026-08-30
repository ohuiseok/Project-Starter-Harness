# AGENTS.md

This repository is an evidence-first harness for external Spring projects. It
covers the whole life of a project: creating one from an empty repository,
understanding an existing one, changing it, and verifying the change.

The users are beginners. They should be able to work in natural language only
and never type a command.

This file holds the rules that apply in **every** mode. Rules that differ by
mode live in `modes/`. Do not restate either set anywhere else; `docs/` and the
skills link here.

## Modes

Two modes, because a beginner starting a toy project and a developer touching
production code need opposite defaults. Read the mode file before acting.

| Mode | File | When |
|---|---|---|
| start | `modes/start.md` | empty or README-only repo; create and learn |
| maintain | `modes/maintain.md` | existing codebase; understand, change, verify |

Never apply `modes/maintain.md` approval gates to a beginner's empty project,
and never apply `modes/start.md` "proceed on the recommendation" to existing
code someone depends on.

## Routing

The user says only `시작해줘`. Decide the mode from preflight, not by asking.

```text
scripts/check-target --target <target-path>

  SPRING_PROJECT: no       → start mode. Do not ask; the intent is unambiguous.
  SPRING_PROJECT: yes      → maintain mode. Ask one short question to pick the
                             skill: 이해 / 수정 / 검증.
  SPRING_PROJECT: UNKNOWN  → ask one short question.
```

A beginner cannot describe their intent in technical terms. Where preflight
already answers the question, do not ask it.

## Non-Negotiable Rules

These hold in both modes.

- The target repository is external. Never create target source inside this
  Harness repository, and never use `workspace/target-solution`.
- All target commands must use the target repository root as the explicit
  working directory.
- Do not mix Harness Git state with target Git state.
- Confirm target preflight before reading target Git state: `TARGET_EXISTS`,
  `TARGET_IS_DIRECTORY`, `TARGET_IS_GIT_REPOSITORY`,
  `TARGET_IS_HARNESS_REPO: no`, `TARGET_GIT_ROOT`, `TARGET_BRANCH`.
- Protect existing dirty changes. Do not overwrite files you did not change.
- If evidence is missing, or a script fails, report `UNKNOWN`. Do not infer the
  missing result.
- Do not store passwords, tokens, API keys, credentials, PII, production
  customer data, full production logs, or secret-bearing config in this
  repository or in anything it generates.
- Do not modify `/root/project-analysis-harness`. It is the read-only source
  this harness was merged from.

## Scripts

These are agent tools. The user never runs them and the README does not show
them. Always pass the target root explicitly.

```bash
scripts/check-environment                            # local Java and Git
scripts/check-target --target <target-path>          # target preflight, routing
scripts/check-spring-project --target <target-path>  # layout details
scripts/run-verification --target <target-path>      # tests
```

Maintain mode adds `map-codebase`, `find-entrypoints`, `find-persistence-links`,
`build-context-pack`, `detect-changes`, `stale-candidates`, `daily-check`, and
`install-target-hooks`. See `docs/skills-and-scripts.md`.

Run `check-environment` before the first session of a project. A beginner may
not have Java installed at all, and that must be reported up front rather than
discovered halfway through an implementation.

If no `--target` is given, the scripts fall back to the `target.repository`
value in `config/target.local.yaml`. That file is git-ignored and holds one
user's own path.

`tests/run-tests` covers the scripts themselves. Run it after changing anything
under `scripts/`.

## Git Safety

Before editing a target repo:

- Run target preflight.
- Check target Git status.
- Check Harness Git status separately when changing Harness files.
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
