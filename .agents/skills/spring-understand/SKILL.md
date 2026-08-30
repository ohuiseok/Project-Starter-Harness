---
name: spring-understand
description: Use for Spring/Spring Boot/MyBatis/JPA project onboarding, learning, investigation, codebase understanding, context pack creation, and root cause analysis. Do not use for source modification.
---

# Spring Understand

Use this skill when the user asks to understand, learn, analyze, investigate, or
build context for an external Spring target repository.

## Rules

Follow `AGENTS.md` for the shared rules and `modes/maintain.md` for this mode:
the approval model, evidence separation, customer safety, minimal change and
the auto-check rules. Do not restate them here.

## Workflow

1. Resolve and preflight the target repository.
2. Detect target instructions and project documents as evidence candidates:
   `AGENTS.md`, nested `AGENTS.md`, `README*`, `pom.xml`, `build.gradle*`,
   `settings.gradle*`, `gradlew`, and `mvnw`.
3. Run deterministic scripts only as needed.
4. Treat persistence as technology-neutral until evidence shows JPA, MyBatis,
   JDBC, Mixed, or UNKNOWN.
5. If unreviewed auto-check reports exist, mention them briefly and re-check
   related target evidence when relevant to the task.
6. For long-term learning, prefer the configured baseline branch as the
   reference behavior when available.
7. Build a Context Pack using `templates/context-pack.md`.
8. Separate baseline branch behavior, current branch behavior, and
   intended behavior.
9. For incidents, use `templates/root-cause-analysis.md`.
10. End with evidence, unknowns, and next decision points.

## Safety

Exception location is not Root Cause. Customer scope defaults to `UNKNOWN` until
evidence shows otherwise.
Auto-check recommendation is a hint only; current target code evidence decides
observed behavior.
