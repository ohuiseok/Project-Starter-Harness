# Natural-language continuation

Continuation interprets one user request against the current project brief and
progress evidence. It never authorizes code generation or reuses an approval.
The route stores only a PII-minimized request summary, selected or proposed
feature, separately classified blockers, warnings, and required decisions,
interpretation confidence, and the next existing workflow. Secret-like input is
rejected and rendered user text is Markdown-escaped.

Deterministic evidence wins over language inference. An explicit feature ID is
preferred, then an exact candidate name, then the current recommendation for a
generic next request. Unknown or multiple IDs require clarification. Technology
terms come from the technology catalog rather than only a routing word list.

A new feature atomically reserves the next unused stable ID in target-owned
evidence, but is not added to the project brief until Feature Specification.
Concurrent requests cannot silently claim the same ID.

Completed features route to revision, deferred features route to resume, and
blocked candidates show their dependency or UNKNOWN blockers. Technology
changes go to Technology Selection. Bugs still go through Feature Specification
with change kind `BUG_FIX`. Verification retries return to the latest incomplete
verification workflow.

The user view always permits correction in natural language. Route approval
binds the structured route and rendered view and creates a handoff only. Consume
that validated handoff into one immutable `READY_FOR_WORKFLOW` intake before
starting the named workflow. Neither handoff nor intake approves a feature,
design, execution, apply, runtime effects, Git commit, or push.

For `FEATURE_SPECIFICATION`, create `spec.draft.json` and its change-focused
review first. The draft may contain blocking `UNKNOWN` decisions and does not
replace an approved project brief or feature contract. A revision must bind the
current feature contract explicitly. One immutable receipt claims each intake;
recover only a receipt whose referenced output set is incomplete and whose
remaining artifacts still match their recorded hashes. Natural-language
answers create immutable successor drafts instead of overwriting the initial
draft. Each successor binds its previous hash, preserves source and decision
IDs, and adds provenance for the new answer. Only the unbranched chain head may
advance. Compute all semantic changes, bind them to exactly one PII-minimized
answer source, show before/after values, and reject implicit removal of
confirmed content. A separate readiness report checks name, goal, user value, actors, trigger, main
flow, acceptance criteria, blocking unknowns, design decisions, and
unconfirmed AI proposals. Once ready, reuse the normal feature validator,
renderer, and approval recorder. Draft updates use a `PREPARED` journal before
writing successor artifacts and become `COMMITTED` only after their exact
draft and view exist; interrupted updates require exact recovery.
Cancellation creates immutable evidence, deletes no draft history, and prevents
the cancelled intake from advancing further.

Promotion is a separate final boundary. Rebuild and review the exact project
candidate delta and official feature destination, then bind explicit approval
to that plan and view. Revalidate readiness and all upstream hashes immediately
before a journaled atomic write of approved project/feature JSON and Markdown.
Record a separate immutable `CONSUMED` receipt. Promotion never authorizes
design artifacts, source generation, runtime effects, or Git operations.
