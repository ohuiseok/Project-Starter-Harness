# Relational Artifact Dry Runs

Run this milestone only for an approved, current PostgreSQL + Flyway physical
contract. The artifact plan supplies rendering details that cannot safely be
inferred: database name, credential-secret roles, and the Testcontainers Java
path/class. It pins the physical contract, physical model, and technology
profile by SHA-256.

The renderer creates Flyway SQL, Compose YAML, and optional Testcontainers Java
only in temporary storage. It compares those bytes with the target. Missing
files are `CREATE`; existing bytes are `UNCHANGED` only when exact; every other
existing file is `CONFLICT` until an approved relational baseline owns it. It
does not write target source, connect to a database, start containers, execute
migrations or tests, create volumes, or reserve ports.

The report must expose generated paths and hashes, conflicts, recovery evidence,
and separate file-application approval from later database/container execution.
DDL is classified transactionally only when it contains the supported CREATE
subset. This dry run is not proof that a future migration succeeds against a
real PostgreSQL instance; that requires a later isolated execution milestone.

After the exact report is displayed, file application requires a separate
approval containing its SHA-256 and canonical target. Apply revalidates every
contract input, independently re-renders all bytes, and rechecks target hashes
and modes immediately before each atomic replacement. Replaced files, the
report, approval, artifact plan, and prior relational baseline are backed up.
Partial failure rolls back files and baseline. Success writes the separate
`.starter-harness-relational.json` ownership baseline last. Applying files never
authorizes or runs Flyway, Docker, Testcontainers, tests, ports, or database I/O.
