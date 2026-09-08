# Natural-language continuation

Continuation interprets one user request against the current project brief and
progress evidence. It never authorizes code generation or reuses an approval.
The route records the original request, selected or proposed feature, blockers,
interpretation confidence, and the next existing workflow.

Deterministic evidence wins over language inference. An explicit feature ID is
preferred, then an exact candidate name, then the current recommendation for a
generic next request. A new feature receives the next unused stable ID but is
not added to the project brief until the Feature Specification workflow.

Completed features route to revision, deferred features route to resume, and
blocked candidates show their dependency or UNKNOWN blockers. Technology
changes go to Technology Selection. Bugs still go through Feature
Specification with change kind `BUG_FIX`. Verification retries return to the
latest incomplete verification workflow. Ambiguous or low-confidence routes
require one confirmation; the user view always permits correction in natural
language. Route approval binds the structured route and rendered view and
creates a handoff only—it does not approve a feature, design, execution, apply,
runtime effects, Git commit, or push.
