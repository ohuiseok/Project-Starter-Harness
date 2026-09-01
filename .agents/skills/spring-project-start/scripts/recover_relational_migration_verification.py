#!/usr/bin/env python3
"""Safely remove Docker resources recorded by an interrupted verification."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

from run_relational_migration_verification import JOURNAL_PATH, RESOURCE_LABEL, atomic_json, run, validate_storage
from validate_feature_specs import load_object


SUFFIX = re.compile(r"^[a-f0-9]{12}$")


def validate_journal(document: dict, target: Path) -> tuple[str, list[str], str]:
    if not isinstance(document, dict): raise ValueError("migration verification journal is invalid")
    required = {"migrationVerificationJournalVersion", "state", "target", "planSha256", "planId", "createdAt", "label", "resources"}
    if document.get("state") == "CLEANUP_REQUIRED": required.add("cleanup")
    journal_version = document.get("migrationVerificationJournalVersion")
    if set(document) != required or journal_version not in {1, 2}: raise ValueError("migration verification journal is invalid")
    if document["state"] not in {"RUNNING", "CLEANUP_REQUIRED"} or Path(str(document["target"])).resolve() != target: raise ValueError("migration verification journal target or state is invalid")
    if document["label"] != RESOURCE_LABEL: raise ValueError("migration verification resource label is invalid")
    resources = document["resources"]
    if not isinstance(resources, dict) or set(resources) != {"network", "databaseContainer", "flywayContainers"}: raise ValueError("migration verification resources are invalid")
    flyway = resources["flywayContainers"]
    actions = {1: {"migrate", "validate"}, 2: {"migrate", "validate", "info"}}[journal_version]
    if not isinstance(flyway, dict) or set(flyway) != actions: raise ValueError("migration verification Flyway resources are invalid")
    match = re.fullmatch(r"harness-verify-([a-f0-9]{12})", resources["network"] if isinstance(resources["network"], str) else "")
    if not match or not SUFFIX.fullmatch(match.group(1)): raise ValueError("migration verification network name is unsafe")
    suffix = match.group(1); expected_database = f"harness-postgres-{suffix}"; expected_flyway = {action: f"harness-flyway-{action}-{suffix}" for action in actions}
    if resources["databaseContainer"] != expected_database or flyway != expected_flyway: raise ValueError("migration verification resource names do not share the journal suffix")
    return resources["network"], [expected_database, *(flyway[action] for action in sorted(actions))], suffix


def labeled(resource_type: str, name: str) -> bool | None:
    template = "{{ index .Labels \"starter-harness.relational-verification\" }}" if resource_type == "network" else "{{ index .Config.Labels \"starter-harness.relational-verification\" }}"
    result = run(["docker", resource_type, "inspect", "--format", template, name], 20) if resource_type == "network" else run(["docker", "inspect", "--format", template, name], 20)
    if result.returncode and ("not found" in result.stderr.lower() or "no such" in result.stderr.lower()): return None
    if result.returncode: raise ValueError(f"could not inspect Docker {resource_type} {name}")
    return result.stdout.strip().lower() == "true"


def recover(target: Path) -> dict:
    root = target.resolve(strict=True)
    validate_storage(root)
    journal_path = root / JOURNAL_PATH
    if journal_path.is_symlink() or not journal_path.is_file(): raise ValueError("no safe pending migration verification journal exists")
    document = load_object(journal_path); network, containers, suffix = validate_journal(document, root)
    removed: dict[str, bool] = {}
    for name in containers:
        ownership = labeled("container", name)
        if ownership is False: raise ValueError(f"refusing to remove unlabeled Docker container: {name}")
        if ownership is None: removed[name] = True
        else:
            result = run(["docker", "rm", "--force", name], 30); removed[name] = result.returncode == 0 or "no such" in result.stderr.lower()
    ownership = labeled("network", network)
    if ownership is False: raise ValueError(f"refusing to remove unlabeled Docker network: {network}")
    if ownership is None: removed[network] = True
    else:
        result = run(["docker", "network", "rm", network], 30); removed[network] = result.returncode == 0 or "not found" in result.stderr.lower()
    if not all(removed.values()): raise ValueError("some recorded Docker resources could not be removed")
    report = {**document, "state": "RECOVERED", "recoveredAt": dt.datetime.now(dt.timezone.utc).isoformat(), "removed": removed}
    report.pop("cleanup", None)
    destination = root / ".starter-harness/verification/recovered" / f"{suffix}.json"
    if destination.exists(): raise ValueError("recovery evidence already exists")
    atomic_json(report, destination); journal_path.unlink()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--target", required=True, type=Path); args = parser.parse_args()
    try: result = recover(args.target)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error: print(f"RELATIONAL_MIGRATION_RECOVERY_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    print("RELATIONAL_MIGRATION_RECOVERY_VALID: yes"); print("RECOVERY_STATE: RECOVERED"); print(f"REMOVED_OR_CONFIRMED_ABSENT: {len(result['removed'])}"); return 0


if __name__ == "__main__": sys.exit(main())
