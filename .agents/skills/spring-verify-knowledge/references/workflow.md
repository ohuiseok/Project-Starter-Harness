# Spring Verify Knowledge Workflow

Use this reference for review, verification, sync, and Knowledge proposal work.

1. Resolve and preflight the target repository.
2. Check the target diff from the target root.
3. Check `reports/auto-check/unreviewed/*.md` and `reports/auto-check/latest.md`
   when present. Reading a report does not mark it reviewed.
4. Identify changed files and stale Knowledge candidates.
5. Verify build, tests, API, persistence, customer impact, and rollback notes as
   relevant.
6. Produce a verification report.
7. If long-term context should be kept, produce a Knowledge Proposal.
8. Do not update Knowledge without human approval.
