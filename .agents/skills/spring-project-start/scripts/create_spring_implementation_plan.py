#!/usr/bin/env python3
"""Create a source-free Spring implementation plan from approved evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from spring_implementation_plan import build, ref, validate
from validate_feature_specs import load_object
from http_api_contract import validate_http_contract
from relational_physical_contract import validate_physical_contract
from render_relational_migration_verification_report import validate as validate_migration_report


def atomic(document: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle: json.dump(document, handle, ensure_ascii=False, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("feature", "profile", "route", "http-api-contract", "openapi", "physical-contract", "physical-model", "migration-verification", "target", "output"): parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--package-name", required=True); args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        output = args.output.resolve(strict=False)
        if not root.is_dir() or args.target.is_symlink() or root not in output.parents or args.output.exists() or args.output.is_symlink(): raise ValueError("target or output is unsafe")
        paths = {"featureSpec": args.feature, "technologyProfile": args.profile, "designRoute": args.route, "httpApiContract": args.http_api_contract, "openApi": args.openapi, "physicalContract": args.physical_contract, "physicalModel": args.physical_model, "migrationVerification": args.migration_verification}
        refs = {name: ref(path, root) for name, path in paths.items()}; feature, profile, route, http_contract, openapi, physical_contract, physical, migration = (load_object(path) for path in paths.values())
        api_approved, api_blockers, validated_api = validate_http_contract(http_contract, route, args.route, root, args.http_api_contract, feature, profile)
        logical_contract = root / physical_contract["logicalContract"]["path"]
        physical_approved, physical_blockers, validated_physical, _ = validate_physical_contract(physical_contract, args.physical_model, logical_contract, route, args.route, root, feature, profile)
        validate_migration_report(migration, args.migration_verification, root)
        if not api_approved or api_blockers or validated_api != openapi: raise ValueError("HTTP API contract is not approved and current: " + "; ".join(api_blockers))
        if not physical_approved or physical_blockers or validated_physical != physical: raise ValueError("physical contract is not approved and current: " + "; ".join(physical_blockers))
        plan = build(feature, profile, route, openapi, physical, migration, root, args.package_name, refs)
        if migration.get("result", {}).get("state") != "PASSED" or migration.get("result", {}).get("schemaFingerprint", {}).get("state") != "MATCHED": plan["conflicts"].append({"code": "MISSING_CONTRACT", "severity": "BLOCKING", "subject": "migrationVerification", "message": "통과한 migration과 schema fingerprint 증거가 필요합니다.", "recommendedActions": ["격리 migration 검증 실행"], "evidencePaths": [refs["migrationVerification"]["path"]]}); plan["status"] = "BLOCKED"
        blockers = validate(plan, root)
        if blockers and plan["status"] == "REVIEW_READY": raise ValueError("generated plan unexpectedly has blockers: " + "; ".join(blockers))
        atomic(plan, output)
    except (OSError, ValueError, KeyError) as error: print(f"SPRING_IMPLEMENTATION_PLAN_CREATED: no\nERROR: {error}", file=sys.stderr); return 1
    print("SPRING_IMPLEMENTATION_PLAN_CREATED: yes"); print(f"PLAN_STATUS: {plan['status']}"); print("TARGET_SOURCE_CHANGED: no"); return 0


if __name__ == "__main__": sys.exit(main())
