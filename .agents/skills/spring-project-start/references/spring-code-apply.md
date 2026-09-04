# Spring Code Apply

Only code with a current, passing isolated verification can reach apply review.
The basic view shows user value, CREATE/UPDATE counts, verification, relevant
Git overlap, unrelated dirty warnings, backup and recovery effects, and actions
that remain excluded. Hashes stay internal.

Apply approval binds the exact dry run, verification report, target context,
current cumulative baseline, and complete file set. Apply revalidates them
immediately before writing. Existing baseline entries outside the current slice
are retained. A user-owned or drifted path is never overwritten.

The transaction records PREPARED, APPLYING, and COMMITTED. Failures recover to
RECOVERED when exact before/after evidence permits it; ambiguous drift produces
RECOVERY_FAILED and forbids overwrite. An active transaction blocks new apply.
Apply and post-apply verification are distinct. A successful apply does not run
target tests, create a Git commit, or push.
