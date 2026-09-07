# Spring Milestone Completion

Completion closes the loop from approved requirements to applied files and
executed tests. It does not rewrite approved feature or project contracts.
Instead, a cumulative progress ledger records execution state while preserving
the hashes of all upstream evidence.

A milestone is `APPLIED_PREVERIFIED` only when the committed apply transaction,
current cumulative implementation baseline, actual file hashes and modes,
passing isolated verification, and requirement-to-component-to-test links all
match. The full wrapper test command is aggregate execution evidence for the
candidate; it does not claim that every test method ran or that post-apply
runtime verification occurred.

`docs/progress.json` is the machine-readable ledger and `docs/progress.md` is its
user view. The view starts with the completed user value, verification outcome,
remaining unknowns, and the next eligible feature. Candidates are eligible only
when they are not completed or deferred, their dependencies are completed, and
they have no blocking unknown links. Users may accept the recommendation, pick
another candidate, describe the next feature in natural language, or revise an
existing feature.
