#!/usr/bin/env python3
"""Migrate a legacy single-file verification plan to an unapproved v2 chain."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath

from run_relational_migration_verification import VERSIONED_FILE, atomic_json
from validate_feature_specs import load_object


def migrate(document: dict) -> dict:
    required = {"migrationVerificationPlanVersion", "planId", "target", "relationalBaseline", "migration", "database", "images", "limits", "isolation"}
    if not isinstance(document, dict) or set(document) != required or document.get("migrationVerificationPlanVersion") != 1: raise ValueError("source must be an exact version 1 migration verification plan")
    migration = document["migration"]
    if not isinstance(migration, dict) or set(migration) != {"path", "sha256"} or not isinstance(migration["path"], str): raise ValueError("legacy migration reference is invalid")
    filename = VERSIONED_FILE.fullmatch(PurePosixPath(migration["path"]).name)
    if not filename: raise ValueError("legacy migration filename is not a supported versioned Flyway SQL filename")
    version = ".".join(str(int(part)) for part in re.split(r"[._]", filename.group(1)))
    migrated = {key: value for key, value in document.items() if key != "migration"}
    migrated["migrationVerificationPlanVersion"] = 2
    migrated["migrations"] = [{"version": version, "description": filename.group(2).replace("_", " "), "path": migration["path"], "sha256": migration["sha256"]}]
    return migrated


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); args = parser.parse_args()
    try:
        if args.input.is_symlink() or args.output.is_symlink(): raise ValueError("plan paths must not be symbolic links")
        if args.output.exists(): raise ValueError("output already exists; migration never overwrites a reviewed plan")
        atomic_json(migrate(load_object(args.input)), args.output)
    except (OSError, ValueError) as error: print(f"MIGRATION_VERIFICATION_PLAN_MIGRATED: no\nERROR: {error}", file=sys.stderr); return 1
    print("MIGRATION_VERIFICATION_PLAN_MIGRATED: yes"); print("APPROVAL_REQUIRED: yes"); return 0


if __name__ == "__main__": sys.exit(main())
