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


NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
PLAN_ID = re.compile(r"^[a-z][a-z0-9-]*$")
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*|@sha256:[a-f0-9]{64})$")
MAX_OUTPUT = 12000


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value: object) -> str:
    if not isinstance(value, str): raise ValueError("migration path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value: raise ValueError("migration path is unsafe")
    return value


def validate_plan(plan: dict, plan_path: Path, target: Path) -> tuple[Path, dict]:
    required = {"migrationVerificationPlanVersion", "planId", "target", "relationalBaseline", "migration", "database", "images", "limits", "isolation"}
    if not isinstance(plan, dict) or set(plan) != required or plan["migrationVerificationPlanVersion"] != 1: raise ValueError("migration verification plan is invalid")
    if not isinstance(plan["planId"], str) or not PLAN_ID.fullmatch(plan["planId"]): raise ValueError("verification planId is invalid")
    root = target.resolve(strict=True)
    if Path(str(plan["target"])).resolve() != root: raise ValueError("verification plan target does not match")
    baseline_ref = plan["relationalBaseline"]; baseline_path = root / BASELINE_NAME
    if not isinstance(baseline_ref, dict) or baseline_ref.get("path") != BASELINE_NAME or set(baseline_ref) != {"path", "sha256"}: raise ValueError("verification baseline reference is invalid")
    validate_sha(baseline_ref["sha256"], "verification baseline hash")
    if baseline_path.is_symlink() or not baseline_path.is_file() or sha(baseline_path) != baseline_ref["sha256"]: raise ValueError("relational baseline changed after verification planning")
    validate_existing_baseline(baseline_path); baseline = load_object(baseline_path)
    migration_ref = plan["migration"]
    if not isinstance(migration_ref, dict) or set(migration_ref) != {"path", "sha256"}: raise ValueError("migration reference is invalid")
    migration_name = relative(migration_ref["path"]); migration = root / migration_name
    validate_sha(migration_ref["sha256"], "migration hash")
    if migration.is_symlink() or not migration.is_file() or sha(migration) != migration_ref["sha256"]: raise ValueError("migration changed after verification planning")
    if baseline["files"].get(migration_name) != migration_ref["sha256"]: raise ValueError("migration is not owned by the current relational baseline")
    database = plan["database"]
    if not isinstance(database, dict) or set(database) != {"name", "schema"} or any(not isinstance(database[key], str) or not NAME.fullmatch(database[key]) for key in database): raise ValueError("verification database identifiers are invalid")
    images = plan["images"]
    if not isinstance(images, dict) or set(images) != {"postgres", "flyway"} or any(not isinstance(value, str) or not IMAGE.fullmatch(value) or value.endswith(":latest") for value in images.values()): raise ValueError("verification images must be pinned and non-latest")
    if not re.fullmatch(r"(?:docker\.io/library/)?postgres(?::[^:]+|@sha256:[a-f0-9]{64})", images["postgres"]): raise ValueError("verification PostgreSQL image must use the official postgres repository")
    if not re.fullmatch(r"(?:docker\.io/)?redgate/flyway(?::[^:]+|@sha256:[a-f0-9]{64})", images["flyway"]): raise ValueError("verification Flyway image must use the official redgate/flyway repository")
    limits = plan["limits"]
    if not isinstance(limits, dict) or set(limits) != {"startupTimeoutSeconds", "commandTimeoutSeconds", "tmpfsBytes"}: raise ValueError("verification limits are invalid")
    if not isinstance(limits["startupTimeoutSeconds"], int) or not 10 <= limits["startupTimeoutSeconds"] <= 300 or not isinstance(limits["commandTimeoutSeconds"], int) or not 10 <= limits["commandTimeoutSeconds"] <= 600 or not isinstance(limits["tmpfsBytes"], int) or not 64 * 1024 * 1024 <= limits["tmpfsBytes"] <= 2 * 1024 * 1024 * 1024: raise ValueError("verification limits are outside safe bounds")
    expected_isolation = {"publishPorts": False, "persistentVolumes": False, "targetDatabaseAccess": False, "cleanupRequired": True}
    if plan["isolation"] != expected_isolation: raise ValueError("verification isolation guarantees are invalid")
    if plan_path.is_symlink() or root not in (plan_path.resolve(), *plan_path.resolve().parents): raise ValueError("verification plan must be a target-owned regular file")
    return migration, baseline


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


def bounded(value: str, secret: str) -> str: return value.replace(secret, "[REDACTED]")[-MAX_OUTPUT:]


def execute(plan: dict, migration: Path) -> dict:
    suffix = secrets.token_hex(6); network = f"harness-verify-{suffix}"; database_container = f"harness-postgres-{suffix}"; password = secrets.token_urlsafe(32); user = "harness_verify"; database = plan["database"]["name"]; timeout = plan["limits"]["commandTimeoutSeconds"]
    flyway_containers = {action: f"harness-flyway-{action}-{suffix}" for action in ("migrate", "validate")}
    events = []; cleanup = {"databaseContainerRemoved": False, "flywayContainersRemoved": False, "networkRemoved": False}; env_file_name = None; migration_stage = tempfile.TemporaryDirectory(prefix="harness-migration-")
    try:
        staged_migration = Path(migration_stage.name) / migration.name; shutil.copy2(migration, staged_migration)
        with tempfile.NamedTemporaryFile("w", prefix="harness-flyway-", suffix=".env", delete=False) as env_file:
            env_file.write(f"POSTGRES_DB={database}\nPOSTGRES_USER={user}\nPOSTGRES_PASSWORD={password}\nFLYWAY_URL=jdbc:postgresql://{database_container}:5432/{database}\nFLYWAY_USER={user}\nFLYWAY_PASSWORD={password}\nFLYWAY_LOCATIONS=filesystem:/flyway/sql\nFLYWAY_SCHEMAS={plan['database']['schema']}\n")
            env_file_name = env_file.name
        os.chmod(env_file_name, 0o600)
        postgres_tag = plan["images"]["postgres"].rsplit(":", 1)[-1]; major_match = re.match(r"([0-9]+)", postgres_tag); data_path = "/var/lib/postgresql" if major_match and int(major_match.group(1)) >= 18 else "/var/lib/postgresql/data"
        commands = [
            ["docker", "network", "create", "--internal", "--label", "starter-harness.relational-verification=true", network],
            ["docker", "run", "--detach", "--rm", "--name", database_container, "--network", network, "--label", "starter-harness.relational-verification=true", "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "1", "--pids-limit", "512", "--env-file", env_file_name, "--mount", f"type=tmpfs,destination={data_path},tmpfs-size={plan['limits']['tmpfsBytes']}", plan["images"]["postgres"]],
        ]
        for command in commands:
            result = run(command, timeout)
            events.append({"step": command[1] + " " + command[2], "exitCode": result.returncode, "output": bounded(result.stdout + result.stderr, password)})
            if result.returncode: raise ValueError(f"Docker setup failed at {command[1]} {command[2]}")
        deadline = time.monotonic() + plan["limits"]["startupTimeoutSeconds"]
        while True:
            ready = run(["docker", "exec", database_container, "pg_isready", "-U", user, "-d", database], timeout)
            if ready.returncode == 0: break
            if time.monotonic() >= deadline: raise ValueError("isolated PostgreSQL startup timed out")
            time.sleep(0.25)
        mount = f"type=bind,source={Path(migration_stage.name).resolve()},destination=/flyway/sql,readonly"
        for action in ("migrate", "validate"):
            command = ["docker", "run", "--rm", "--name", flyway_containers[action], "--label", "starter-harness.relational-verification=true", "--network", network, "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=67108864", "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "1", "--pids-limit", "512", "--env-file", env_file_name, "--mount", mount, plan["images"]["flyway"], action]
            result = run(command, timeout); events.append({"step": f"flyway {action}", "exitCode": result.returncode, "output": bounded(result.stdout + result.stderr, password)})
            if result.returncode: raise ValueError(f"Flyway {action} failed in isolated PostgreSQL")
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
    result = {"state": state, "events": events, "cleanup": cleanup, "targetDatabaseAccessed": False, "targetSourceFilesChanged": False, "persistentVolumeCreated": False}
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
        plan = load_object(args.plan); migration, _ = validate_plan(plan, args.plan, root); approval = load_object(args.approval); validate_approval(approval, args.plan, root)
        docker = run(["docker", "version", "--format", "{{.Server.Version}}"], 20)
        if docker.returncode: raise ValueError("Docker Engine is unavailable")
        execution = execute(plan, migration)
        report = {"migrationVerificationReportVersion": 1, "plan": {"path": str(args.plan.resolve()), "sha256": sha(args.plan)}, "approval": {"path": str(args.approval.resolve()), "sha256": sha(args.approval), "approvedBy": approval["approvedBy"], "approvedAt": approval["approvedAt"]}, "target": str(root), "executedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "result": execution}
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error: print(f"RELATIONAL_MIGRATION_VERIFICATION_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    print(f"RELATIONAL_MIGRATION_VERIFICATION_VALID: {'yes' if execution['state'] == 'PASSED' else 'no'}"); print(f"VERIFICATION_STATE: {execution['state']}"); print("TARGET_DATABASE_ACCESSED: no"); print("TARGET_SOURCE_FILES_CHANGED: no"); print("PERSISTENT_VOLUME_CREATED: no"); return 0 if execution["state"] == "PASSED" else 1


if __name__ == "__main__": sys.exit(main())
