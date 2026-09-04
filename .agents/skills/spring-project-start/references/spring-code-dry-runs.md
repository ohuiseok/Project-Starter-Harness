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
