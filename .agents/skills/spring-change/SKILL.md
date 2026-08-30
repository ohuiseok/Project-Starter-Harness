---
name: spring-change
description: Use for Spring/Spring Boot/MyBatis/JPA impact analysis, customer impact review, implementation planning, and approved minimal implementation. Do not modify source before explicit human approval.
---

# Spring Change

Use this skill when the user asks to add, change, fix, or implement behavior in
the external Spring target repository.

## Rules

Follow `AGENTS.md` for the shared rules and `modes/maintain.md` for this mode:
the approval model, evidence separation, customer safety, minimal change and
the auto-check rules. Do not restate them here.

## Workflow

1. Start from a Context Pack. If none exists, create one first.
2. Check whether unreviewed auto-check reports exist.
3. Re-check latest target code evidence for auto-check changes that may relate
   to the current task.
4. Identify customer scope and shared areas.
5. If baseline and current branch behavior differ, include that mismatch in the
   plan.
6. Produce a Customer Impact Matrix when customer behavior or common code may be
   affected.
7. Identify tests and verification steps before implementation.
8. Present a minimal implementation plan.
9. Wait for explicit human approval.
10. After approval, make only the approved minimal change.

## Enhanced Review Areas

Shared Service, Shared Mapper, Shared DB, Common Config, Shared API, and Common
Business Rule changes require enhanced impact review.
