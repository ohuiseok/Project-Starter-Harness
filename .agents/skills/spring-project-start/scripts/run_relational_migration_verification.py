#!/usr/bin/env python3
"""Run an exact approved Flyway migration in disposable Docker resources."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

from apply_approved_generation import non_empty, validate_sha
from apply_approved_relational_artifacts import BASELINE_NAME, validate_existing_baseline
from validate_feature_specs import load_object
from validate_feature_specs import validate_approval as validate_document_approval
from relational_physical_contract import validate_physical_model
from relational_schema_fingerprint import actual as actual_schema, catalog_query, differences as schema_differences, expected as expected_schema, fingerprint


NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
PLAN_ID = re.compile(r"^[a-z][a-z0-9-]*$")
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*|@sha256:[a-f0-9]{64})$")
VERSIONED_FILE = re.compile(r"^V([0-9]+(?:[._][0-9]+)*)__([A-Za-z0-9][A-Za-z0-9._-]*)\.sql$")
MAX_OUTPUT = 12000
JOURNAL_PATH = Path(".starter-harness/verification/pending.json")
RESOURCE_LABEL = "starter-harness.relational-verification=true"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value: object) -> str:
    if not isinstance(value, str): raise ValueError("migration path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value: raise ValueError("migration path is unsafe")
    return value


def version_key(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value): raise ValueError("migration version must use canonical numeric dot notation")
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0: parts.pop()
    return tuple(parts)


def target_file_ref(value: object, root: Path, label: str) -> Path:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}: raise ValueError(f"{label} reference is invalid")
    name = relative(value["path"]); validate_sha(value["sha256"], f"{label} hash"); path = root / name; resolved = path.resolve()
    if path.is_symlink() or root not in resolved.parents or not resolved.is_file() or sha(resolved) != value["sha256"]: raise ValueError(f"{label} changed after verification planning or escapes target")
    return resolved


def validate_plan(plan: dict, plan_path: Path, target: Path) -> tuple[list[Path], dict, dict]:
    required = {"migrationVerificationPlanVersion", "planId", "target", "relationalBaseline", "physicalContract", "physicalModel", "migrations", "database", "images", "limits", "isolation"}
    if not isinstance(plan, dict) or set(plan) != required or plan["migrationVerificationPlanVersion"] != 3: raise ValueError("migration verification plan is invalid; migrate legacy plans before approval")
    if not isinstance(plan["planId"], str) or not PLAN_ID.fullmatch(plan["planId"]): raise ValueError("verification planId is invalid")
    root = target.resolve(strict=True)
    if Path(str(plan["target"])).resolve() != root: raise ValueError("verification plan target does not match")
    baseline_ref = plan["relationalBaseline"]; baseline_path = root / BASELINE_NAME
    if not isinstance(baseline_ref, dict) or baseline_ref.get("path") != BASELINE_NAME or set(baseline_ref) != {"path", "sha256"}: raise ValueError("verification baseline reference is invalid")
    validate_sha(baseline_ref["sha256"], "verification baseline hash")
    if baseline_path.is_symlink() or not baseline_path.is_file() or sha(baseline_path) != baseline_ref["sha256"]: raise ValueError("relational baseline changed after verification planning")
    validate_existing_baseline(baseline_path); baseline = load_object(baseline_path)
    contract_path = target_file_ref(plan["physicalContract"], root, "physical contract"); physical_path = target_file_ref(plan["physicalModel"], root, "physical model"); metadata = load_object(contract_path); physical = load_object(physical_path)
    if not isinstance(metadata, dict) or metadata.get("artifact", {}).get("path") != physical_path.relative_to(root).as_posix() or metadata.get("physicalModelSha256") != sha(physical_path) or not validate_document_approval(metadata.get("approval"), "approval", metadata): raise ValueError("physical contract is not approved and current")
    logical_ref = metadata.get("logicalModel"); logical_path = target_file_ref(logical_ref, root, "logical model"); logical = load_object(logical_path); blockers = validate_physical_model(physical, logical, metadata, root)
    if blockers or physical.get("adapterId") != "postgresql-flyway": raise ValueError("physical model is not ready for PostgreSQL schema verification: " + "; ".join(blockers))
    migration_refs = plan["migrations"]
    if not isinstance(migration_refs, list) or not migration_refs: raise ValueError("at least one versioned migration is required")
    migrations = []; migration_names = []; seen_versions = set(); previous = None
    for index, migration_ref in enumerate(migration_refs):
        if not isinstance(migration_ref, dict) or set(migration_ref) != {"version", "description", "path", "sha256"}: raise ValueError(f"migration reference {index + 1} is invalid")
        key = version_key(migration_ref["version"])
        if key in seen_versions: raise ValueError(f"duplicate Flyway migration version: {migration_ref['version']}")
        if previous is not None and key <= previous: raise ValueError("migration chain must be in ascending Flyway version order")
        seen_versions.add(key); previous = key
        migration_name = relative(migration_ref["path"]); migration_path = root / migration_name; migration = migration_path.resolve(); filename = VERSIONED_FILE.fullmatch(migration.name)
        if not filename or tuple(int(part) for part in re.split(r"[._]", filename.group(1))) != key or filename.group(2).replace("_", " ") != migration_ref["description"]: raise ValueError(f"migration identity does not match its Flyway filename: {migration_name}")
        validate_sha(migration_ref["sha256"], f"migration {migration_ref['version']} hash")
        if migration_path.is_symlink() or root not in migration.parents or not migration.is_file() or sha(migration) != migration_ref["sha256"]: raise ValueError(f"migration changed after verification planning or escapes target: {migration_name}")
        if baseline["files"].get(migration_name) != migration_ref["sha256"]: raise ValueError(f"migration is not owned by the current relational baseline: {migration_name}")
        migrations.append(migration); migration_names.append(migration_name)
    parents = {PurePosixPath(name).parent for name in migration_names}
    if len(parents) != 1: raise ValueError("one verification plan must contain one migration directory chain")
    parent = next(iter(parents)); planned_names = set(migration_names); target_version = previous
    required_names = set()
    for owned_name in baseline["files"]:
        owned_path = PurePosixPath(owned_name); match = VERSIONED_FILE.fullmatch(owned_path.name)
        if owned_path.parent == parent and match and version_key(".".join(match.group(1).replace("_", ".").split("."))) <= target_version: required_names.add(owned_name)
    missing = sorted(required_names - planned_names)
    if missing: raise ValueError(f"migration chain omits baseline-owned versioned migration at or below the target: {', '.join(missing)}")
    database = plan["database"]
    if not isinstance(database, dict) or set(database) != {"name", "schema"} or any(not isinstance(database[key], str) or not NAME.fullmatch(database[key]) for key in database): raise ValueError("verification database identifiers are invalid")
    if database["schema"] != physical["database"]["schemaName"]: raise ValueError("verification schema does not match the approved physical model")
    images = plan["images"]
    if not isinstance(images, dict) or set(images) != {"postgres", "flyway"} or any(not isinstance(value, str) or not IMAGE.fullmatch(value) or value.endswith(":latest") for value in images.values()): raise ValueError("verification images must be pinned and non-latest")
    if not re.fullmatch(r"(?:docker\.io/library/)?postgres(?::[^:]+|@sha256:[a-f0-9]{64})", images["postgres"]): raise ValueError("verification PostgreSQL image must use the official postgres repository")
    if not re.fullmatch(r"(?:docker\.io/)?(?:redgate|flyway)/flyway(?::[^:]+|@sha256:[a-f0-9]{64})", images["flyway"]): raise ValueError("verification Flyway image must use an official Redgate-published Flyway repository")
    limits = plan["limits"]
    if not isinstance(limits, dict) or set(limits) != {"startupTimeoutSeconds", "commandTimeoutSeconds", "tmpfsBytes"}: raise ValueError("verification limits are invalid")
    if not isinstance(limits["startupTimeoutSeconds"], int) or not 10 <= limits["startupTimeoutSeconds"] <= 300 or not isinstance(limits["commandTimeoutSeconds"], int) or not 10 <= limits["commandTimeoutSeconds"] <= 600 or not isinstance(limits["tmpfsBytes"], int) or not 64 * 1024 * 1024 <= limits["tmpfsBytes"] <= 2 * 1024 * 1024 * 1024: raise ValueError("verification limits are outside safe bounds")
    expected_isolation = {"publishPorts": False, "persistentVolumes": False, "targetDatabaseAccess": False, "cleanupRequired": True}
    if plan["isolation"] != expected_isolation: raise ValueError("verification isolation guarantees are invalid")
    if plan_path.is_symlink() or root not in (plan_path.resolve(), *plan_path.resolve().parents): raise ValueError("verification plan must be a target-owned regular file")
    return migrations, baseline, physical


def validate_approval(approval: dict, plan_path: Path, target: Path) -> None:
    required = {"migrationVerificationApprovalVersion", "approved", "planSha256", "target", "approvedBy", "approvedAt"}
    if not isinstance(approval, dict) or set(approval) != required or approval["migrationVerificationApprovalVersion"] != 1 or approval["approved"] is not True: raise ValueError("explicit migration verification approval is required")
    if approval["planSha256"] != sha(plan_path): raise ValueError("approval does not match the exact verification plan")
    if Path(str(approval["target"])).resolve() != target.resolve(): raise ValueError("verification approval target does not match")
    if not non_empty(approval["approvedBy"]) or not non_empty(approval["approvedAt"]): raise ValueError("verification approval identity and time are required")
    try: timestamp = dt.datetime.fromisoformat(approval["approvedAt"].replace("Z", "+00:00"))
    except ValueError as error: raise ValueError("verification approval time must be ISO-8601") from error
    if timestamp.utcoffset() is None: raise ValueError("verification approval time must include a timezone")


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def bounded(value: str, secret: str) -> str:
    redacted = value.replace(secret, "[REDACTED]") if secret else value
    return redacted if len(redacted) <= MAX_OUTPUT else f"[앞부분 {len(redacted) - MAX_OUTPUT}자 생략됨]\n" + redacted[-MAX_OUTPUT:]


def progress(stage: str, message: str) -> None: print(f"VERIFICATION_PROGRESS: {stage} · {message}", flush=True)


def prepare_image(reference: str, timeout: int, events: list[dict]) -> dict:
    progress("IMAGE", f"{reference} 준비")
    pulled = run(["docker", "pull", reference], timeout)
    events.append({"step": f"image pull {reference}", "exitCode": pulled.returncode, "output": bounded(pulled.stdout + pulled.stderr, "")})
    if pulled.returncode: raise ValueError(f"Docker image pull failed: {reference}")
    inspected = run(["docker", "image", "inspect", reference], timeout)
    if inspected.returncode: raise ValueError(f"pulled Docker image cannot be inspected: {reference}")
    try: details = json.loads(inspected.stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as error: raise ValueError(f"Docker image evidence is invalid: {reference}") from error
    image_id = details.get("Id"); digests = details.get("RepoDigests") or []
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id) or not isinstance(digests, list) or not all(isinstance(item, str) for item in digests): raise ValueError(f"Docker image identity is invalid: {reference}")
    if "@sha256:" in reference and not any(item.endswith(reference[reference.index("@sha256:"):]) for item in digests): raise ValueError(f"Docker image digest does not match the approved reference: {reference}")
    return {"reference": reference, "imageId": image_id, "repoDigests": sorted(digests)}


def atomic_json(document: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def execution_resources(plan: dict, target: Path, plan_path: Path) -> dict:
    suffix = secrets.token_hex(6)
    return {"migrationVerificationJournalVersion": 2, "state": "RUNNING", "target": str(target), "planSha256": sha(plan_path), "planId": plan["planId"], "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(), "label": RESOURCE_LABEL, "resources": {"network": f"harness-verify-{suffix}", "databaseContainer": f"harness-postgres-{suffix}", "flywayContainers": {action: f"harness-flyway-{action}-{suffix}" for action in ("migrate", "validate", "info")}}}


def validate_storage(root: Path) -> None:
    for directory in (root / ".starter-harness", root / ".starter-harness/verification"):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()): raise ValueError(f"verification evidence directory is unsafe: {directory.relative_to(root)}")


def applied_chain(info_output: str, expected: list[dict]) -> list[dict]:
    try: document = json.loads(info_output)
    except json.JSONDecodeError as error: raise ValueError("Flyway info JSON output is invalid") from error
    migrations = document.get("migrations") if isinstance(document, dict) else None
    if not isinstance(migrations, list): raise ValueError("Flyway info JSON does not contain migrations")
    actual = []
    for item in migrations:
        if not isinstance(item, dict) or item.get("category") != "Versioned": continue
        version = item.get("version"); description = item.get("description"); state = item.get("state")
        if not all(isinstance(value, str) for value in (version, description, state)): raise ValueError("Flyway versioned migration evidence is incomplete")
        actual.append({"version": version, "description": description, "state": state})
    if len(actual) != len(expected): raise ValueError("Flyway applied migration count does not match the approved chain")
    for planned, observed in zip(expected, actual):
        if version_key(observed["version"].replace("_", ".")) != version_key(planned["version"]) or observed["description"] != planned["description"] or observed["state"].lower() != "success": raise ValueError(f"Flyway applied history does not match approved migration {planned['version']}")
    return actual


def execute(plan: dict, migrations: list[Path], physical: dict, journal: dict) -> dict:
    resources = journal["resources"]; network = resources["network"]; database_container = resources["databaseContainer"]; password = secrets.token_urlsafe(32); user = "harness_verify"; database = plan["database"]["name"]; timeout = plan["limits"]["commandTimeoutSeconds"]
    flyway_containers = resources["flywayContainers"]
    events = []; images = {}; expected_fingerprint = expected_schema(physical); schema_evidence = {"state": "NOT_RUN", "expectedSha256": fingerprint(expected_fingerprint), "actualSha256": None, "differences": []}; cleanup = {"databaseContainerRemoved": False, "flywayContainersRemoved": False, "networkRemoved": False}; env_file_name = None; migration_stage = tempfile.TemporaryDirectory(prefix="harness-migration-")
    try:
        for name, reference in plan["images"].items(): images[name] = prepare_image(reference, timeout, events)
        for migration in migrations: shutil.copy2(migration, Path(migration_stage.name) / migration.name)
        with tempfile.NamedTemporaryFile("w", prefix="harness-flyway-", suffix=".env", delete=False) as env_file:
            env_file.write(f"POSTGRES_DB={database}\nPOSTGRES_USER={user}\nPOSTGRES_PASSWORD={password}\nFLYWAY_URL=jdbc:postgresql://{database_container}:5432/{database}\nFLYWAY_USER={user}\nFLYWAY_PASSWORD={password}\nFLYWAY_LOCATIONS=filesystem:/flyway/sql\nFLYWAY_SCHEMAS={plan['database']['schema']}\n")
            env_file_name = env_file.name
        os.chmod(env_file_name, 0o600)
        postgres_tag = plan["images"]["postgres"].rsplit(":", 1)[-1]; major_match = re.match(r"([0-9]+)", postgres_tag); data_path = "/var/lib/postgresql" if major_match and int(major_match.group(1)) >= 18 else "/var/lib/postgresql/data"
        commands = [
            ["docker", "network", "create", "--internal", "--label", RESOURCE_LABEL, network],
            ["docker", "run", "--detach", "--rm", "--name", database_container, "--network", network, "--label", RESOURCE_LABEL, "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "1", "--pids-limit", "512", "--env-file", env_file_name, "--mount", f"type=tmpfs,destination={data_path},tmpfs-size={plan['limits']['tmpfsBytes']}", images["postgres"]["imageId"]],
        ]
        for command in commands:
            result = run(command, timeout)
            events.append({"step": command[1] + " " + command[2], "exitCode": result.returncode, "output": bounded(result.stdout + result.stderr, password)})
            if result.returncode: raise ValueError(f"Docker setup failed at {command[1]} {command[2]}")
        deadline = time.monotonic() + plan["limits"]["startupTimeoutSeconds"]
        progress("DATABASE", "격리 PostgreSQL 준비 대기")
        while True:
            ready = run(["docker", "exec", database_container, "pg_isready", "-U", user, "-d", database], timeout)
            if ready.returncode == 0: break
            if time.monotonic() >= deadline: raise ValueError("isolated PostgreSQL startup timed out")
            time.sleep(0.25)
        mount = f"type=bind,source={Path(migration_stage.name).resolve()},destination=/flyway/sql,readonly"
        applied_migrations = []
        for action in ("migrate", "validate", "info"):
            progress("FLYWAY", action)
            command = ["docker", "run", "--rm", "--name", flyway_containers[action], "--label", RESOURCE_LABEL, "--network", network, "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=67108864", "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "1", "--pids-limit", "512", "--env-file", env_file_name, "--mount", mount, images["flyway"]["imageId"], action]
            if action == "info": command.append("-outputType=json")
            result = run(command, timeout); events.append({"step": f"flyway {action}", "exitCode": result.returncode, "output": bounded(result.stdout + result.stderr, password)})
            if result.returncode: raise ValueError(f"Flyway {action} failed in isolated PostgreSQL")
            if action == "info": applied_migrations = applied_chain(result.stdout, plan["migrations"])
        progress("SCHEMA", "PostgreSQL catalog와 physical model 비교")
        catalog = run(["docker", "exec", database_container, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-U", user, "-d", database, "-c", catalog_query(plan["database"]["schema"])], timeout)
        events.append({"step": "schema catalog fingerprint", "exitCode": catalog.returncode, "output": bounded(catalog.stdout + catalog.stderr, password)})
        if catalog.returncode: raise ValueError("PostgreSQL schema catalog extraction failed")
        try: observed_fingerprint = actual_schema(json.loads(catalog.stdout), plan["database"]["schema"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error: raise ValueError("PostgreSQL schema catalog evidence is invalid") from error
        differences = schema_differences(expected_fingerprint, observed_fingerprint); schema_evidence = {"state": "MATCHED" if not differences else "MISMATCHED", "expectedSha256": fingerprint(expected_fingerprint), "actualSha256": fingerprint(observed_fingerprint), "differences": differences}
        if differences: raise ValueError(f"PostgreSQL schema differs from the approved physical model at {len(differences)} path(s)")
        state = "PASSED"
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        state = "FAILED"; failure = str(error)
    finally:
        if env_file_name:
            try: Path(env_file_name).unlink(missing_ok=True)
            except OSError: pass
        migration_stage.cleanup()
        try:
            removed = run(["docker", "rm", "--force", database_container], 30); cleanup["databaseContainerRemoved"] = removed.returncode == 0 or "No such container" in removed.stderr
        except (OSError, subprocess.TimeoutExpired): cleanup["databaseContainerRemoved"] = False
        flyway_removed = []
        for container in flyway_containers.values():
            try:
                removed = run(["docker", "rm", "--force", container], 30); flyway_removed.append(removed.returncode == 0 or "No such container" in removed.stderr)
            except (OSError, subprocess.TimeoutExpired): flyway_removed.append(False)
        cleanup["flywayContainersRemoved"] = all(flyway_removed)
        try:
            removed = run(["docker", "network", "rm", network], 30); cleanup["networkRemoved"] = removed.returncode == 0 or "not found" in removed.stderr.lower()
        except (OSError, subprocess.TimeoutExpired): cleanup["networkRemoved"] = False
    if not all(cleanup.values()): state = "CLEANUP_FAILED"; failure = "isolated Docker resources could not be fully removed"
    progress("CLEANUP", "임시 Docker 자원 정리 확인")
    result = {"state": state, "events": events, "cleanup": cleanup, "images": images, "appliedMigrations": applied_migrations if "applied_migrations" in locals() else [], "schemaFingerprint": schema_evidence, "targetDatabaseAccessed": False, "targetSourceFilesChanged": False, "persistentVolumeCreated": False}
    if state != "PASSED": result["failure"] = failure
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--plan", required=True, type=Path); parser.add_argument("--approval", required=True, type=Path); parser.add_argument("--target", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        if args.target.is_symlink() or root == Path(__file__).resolve().parents[4]: raise ValueError("target must be an external non-symlink repository")
        for path, label in ((args.plan, "plan"), (args.approval, "approval"), (args.output, "output")):
            if path.is_symlink(): raise ValueError(f"{label} must not be a symbolic link")
            if root not in (path.resolve(), *path.resolve().parents): raise ValueError(f"{label} escapes target")
        if args.output.exists(): raise ValueError("verification output already exists")
        validate_storage(root); journal_path = root / JOURNAL_PATH
        if journal_path.exists(): raise ValueError(f"unfinished migration verification journal exists: {JOURNAL_PATH}; recover it before retrying")
        plan = load_object(args.plan); migrations, _, physical = validate_plan(plan, args.plan, root); approval = load_object(args.approval); validate_approval(approval, args.plan, root)
        docker = run(["docker", "version", "--format", "{{.Server.Version}}"], 20)
        if docker.returncode: raise ValueError("Docker Engine is unavailable")
        journal = execution_resources(plan, root, args.plan); atomic_json(journal, journal_path)
        execution = execute(plan, migrations, physical, journal)
        if execution["state"] == "CLEANUP_FAILED":
            journal["state"] = "CLEANUP_REQUIRED"; journal["cleanup"] = execution["cleanup"]; atomic_json(journal, journal_path)
        report = {"migrationVerificationReportVersion": 4, "plan": {"path": str(args.plan.resolve()), "sha256": sha(args.plan)}, "approval": {"path": str(args.approval.resolve()), "sha256": sha(args.approval), "approvedBy": approval["approvedBy"], "approvedAt": approval["approvedAt"]}, "target": str(root), "executedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "runtime": {"dockerServerVersion": docker.stdout.strip()}, "result": execution}
        atomic_json(report, args.output)
        if execution["state"] != "CLEANUP_FAILED": journal_path.unlink()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error: print(f"RELATIONAL_MIGRATION_VERIFICATION_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    print(f"RELATIONAL_MIGRATION_VERIFICATION_VALID: {'yes' if execution['state'] == 'PASSED' else 'no'}"); print(f"VERIFICATION_STATE: {execution['state']}"); print("TARGET_DATABASE_ACCESSED: no"); print("TARGET_SOURCE_FILES_CHANGED: no"); print("PERSISTENT_VOLUME_CREATED: no"); return 0 if execution["state"] == "PASSED" else 1


if __name__ == "__main__": sys.exit(main())
