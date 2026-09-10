# Spring Code Dry Runs

A code dry run reviews an exact candidate implementation without applying it.
The candidate is rendered in temporary storage by the agent and must match every
component and path in an approved implementation plan. Extra and missing files
are blocking, even when they look useful.

The first milestone accepts Java files only. It checks package and public type
identity, required Spring stereotypes, the service-owned write transaction,
API/entity separation, API path, persistence names, component collaboration,
executable assertions, and requirement references. These static checks are not
proof that code compiles or behaves correctly.

The user view begins with behavior, change counts, architecture checks, and
unresolved conflicts. Exact source previews and SHA-256 values are details.
A clear report is reviewable but never executable. Exact report approval permits
only `run_spring_code_verification.py`, which copies the target, overlays the
candidate, hides the Docker socket, disables networking with bubblewrap, and
runs the wrapper tests offline. A passing verification permits review of a later
apply approval; it does not apply files. Updates require the canonical
implementation baseline; an unrelated existing file is always a conflict.

Plan v2 first passes a separate source-free renderability assessment. It binds
the exact plan approval, current build evidence, relevant Git overlap, supported
schema subset, conservative file/total limits, and the dedicated
`.starter-harness-implementation-v2.json` manifest. It labels contract coverage
separately from business behavior and does not activate a renderer. Existing
file UPDATE remains blocked until symbol-preserving structural validation is
implemented; never fall back to regex replacement or whole-file overwrite.
Dependency evidence comes from parsed Gradle/Maven declarations, not comments.
Git overlap is module-aware and NUL-safe. Recheck the content and mode of every
v2 baseline-managed file and report drift before rendering. Planning may combine
reused and added methods in an evidence-backed existing Controller or service,
while rendering that UPDATE stays closed. Unsupported media types, parameter
locations, unresolved references, response headers, and 204 body rules are part
of the semantic readiness assessment.

The first v2 renderer is `JAVA_MVC_API_ONLY_V1`. Activating it changes the
capability-catalog hash, so an older plan and its approval can never silently
gain rendering authority. Rebuild and approve the plan after that catalog
change. Plan approval authorizes candidate preparation only. The renderer
accepts agent-prepared Java candidates from a non-symlink directory, supports
only `CREATE_FILE` and evidence-only `REUSE_FILE`, and keeps `UPDATE_FILE`
blocked. It checks exact file coverage, Java identity, Spring roles, composed
MVC mappings, parameters, request validation, response status, DTO shape,
service operation names, executable test assertions, requirement traceability,
secret-like literals, target collisions, candidate limits, and reuse hashes.
The report binds the exact plan approval, renderability report, embedded source
and desired v2 manifest. A separate exact dry-run approval authorizes only a
future isolated verification; it never authorizes source application.

V2 isolated verification starts with an immutable execution plan. It binds the
exact dry-run approval, target source/build/wrapper context, wrapper command,
local offline-cache presence, Java evidence, sandbox availability, effects,
timeout, and output limit. Show its user-first view and obtain a separate exact
approval. The runner reconstructs embedded candidates in an allowlist-only
temporary copy, copies dependency artifacts but never Maven/Gradle credential
settings, clears the environment, hides home and common secret-bearing paths,
unshares all namespaces, disables networking, and points Docker at a nonexistent
socket. Timeouts, unavailable offline artifacts, and redacted secret-like output
are `UNKNOWN`, while ordinary compilation or test failures are `FAILED`.
Journal `PREPARED` and `RUNNING` before execution; interrupted work must be
recovered by exact temporary-root and process evidence. A passing report permits
only a later apply review, not apply itself.

Before approval, hash a bounded canonical manifest of every cache artifact and
reject incomplete scans or symlinks. Recheck it immediately before and after
copying. Bind branch, HEAD, relevant dirty paths, Java compatibility, resources,
Gradle build logic/version catalogs and Maven wrapper extensions into the plan.
Dynamic or external build-script inputs, unsafe resource types, secret-like
inputs and scan-limit exhaustion are blockers. The sandbox mounts only required
system runtime trees; it never mounts host `/` or the actual target. Store PID
start ticks and stop the exact process group before recovery deletes temporary
storage. Decode output defensively, remove terminal control sequences, and turn
secret-like or PII-like output into redacted `UNKNOWN`.

Historical report validation and current apply readiness are different checks.
A later cache cleanup or sandbox change must not erase valid execution evidence.
`validate_spring_code_verification_apply_readiness_v2.py` separately rechecks
the current dry run, target content, branch, HEAD, and relevant dirty paths
immediately before an apply review.
