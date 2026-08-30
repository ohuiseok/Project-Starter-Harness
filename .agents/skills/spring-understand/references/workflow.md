# Spring Understand Workflow

Use this reference for onboarding, learning, investigation, and Context Pack
creation.

1. Start with the user's task or symptom.
2. Resolve the target repository path.
3. Run target preflight.
4. Detect target instructions and build files.
5. Check for unreviewed auto-check reports and mention related candidates.
6. Search for entry points with `scripts/find-entrypoints`.
7. Search persistence links with `scripts/find-persistence-links` when JPA,
   MyBatis, JDBC, DB, repository, mapper, entity, query, or transaction
   behavior matters.
8. Separate baseline branch behavior, current branch behavior, and intended
   behavior when branch context is available.
9. Record evidence and unknowns.
10. Produce a Context Pack or RCA.

For learning tasks, include Self Check questions that require the developer to
open and read actual target files.
