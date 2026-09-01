#!/usr/bin/env python3
"""Attach approved physical evidence to a legacy verification plan draft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from migrate_relational_migration_verification_plan_v2 import migrate as migrate_v2
from run_relational_migration_verification import atomic_json, sha, validate_plan
from validate_feature_specs import load_object


def migrate(document: dict, physical_contract: Path, physical_model: Path, target: Path) -> dict:
    if document.get("migrationVerificationPlanVersion") == 1: document = migrate_v2(document)
    if not isinstance(document, dict) or document.get("migrationVerificationPlanVersion") != 2 or "physicalContract" in document or "physicalModel" in document: raise ValueError("source must be an exact legacy version 1 or version 2 plan")
    root = target.resolve(strict=True); result = dict(document); result["migrationVerificationPlanVersion"] = 3
    for key, path in (("physicalContract", physical_contract), ("physicalModel", physical_model)):
        resolved = path.resolve(strict=True)
        if path.is_symlink() or root not in resolved.parents or not resolved.is_file(): raise ValueError(f"{key} must be a target-owned regular file")
        result[key] = {"path": resolved.relative_to(root).as_posix(), "sha256": sha(resolved)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", required=True, type=Path); parser.add_argument("--physical-contract", required=True, type=Path); parser.add_argument("--physical-model", required=True, type=Path); parser.add_argument("--target", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); args = parser.parse_args()
    try:
        if args.input.is_symlink() or args.output.is_symlink() or args.output.exists(): raise ValueError("migration paths are unsafe or output already exists")
        result = migrate(load_object(args.input), args.physical_contract, args.physical_model, args.target)
        atomic_json(result, args.output); validate_plan(result, args.output, args.target)
    except (OSError, ValueError) as error:
        if args.output.exists(): args.output.unlink()
        print(f"MIGRATION_VERIFICATION_PLAN_V3_MIGRATED: no\nERROR: {error}", file=sys.stderr); return 1
    print("MIGRATION_VERIFICATION_PLAN_V3_MIGRATED: yes"); print("APPROVAL_REQUIRED: yes"); return 0


if __name__ == "__main__": sys.exit(main())
