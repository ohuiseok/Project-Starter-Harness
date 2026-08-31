#!/usr/bin/env python3
"""Convert a legacy feature spec to v2 without changing the source file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from validate_feature_specs import load_object, validate_feature


LEGACY_KEYS = {
    "httpApi", "relationalData", "messaging", "scheduledJob",
    "serverRenderedUi", "separateClient", "externalIntegration",
}


def migrated_decision(enabled: bool) -> dict[str, Any]:
    if enabled:
        return {
            "status": "REQUIRED",
            "reason": "Legacy v1 marked this as required; confirm the meaning.",
            "source": "INFERRED",
            "confirmedByUser": False,
        }
    return {
        "status": "UNKNOWN",
        "reason": "Legacy v1 false did not distinguish not needed from undecided.",
        "source": "UNKNOWN",
        "confirmedByUser": False,
    }


def migrate(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schemaVersion") != 1:
        raise ValueError("input must be a legacy feature schemaVersion 1 document")
    legacy = document.get("designNeeds")
    if not isinstance(legacy, dict) or set(legacy) != LEGACY_KEYS:
        raise ValueError(f"designNeeds must contain exactly {sorted(LEGACY_KEYS)}")
    if not all(isinstance(value, bool) for value in legacy.values()):
        raise ValueError("all legacy designNeeds values must be boolean")
    converted = json.loads(json.dumps(document))
    converted["schemaVersion"] = 2
    converted.pop("designNeeds")
    converted["designRequirements"] = {
        "httpApi": migrated_decision(legacy["httpApi"]),
        "persistentState": migrated_decision(legacy["relationalData"]),
        "messaging": migrated_decision(legacy["messaging"]),
        "scheduledJob": migrated_decision(legacy["scheduledJob"]),
        "serverRenderedUi": migrated_decision(legacy["serverRenderedUi"]),
        "separateClient": migrated_decision(legacy["separateClient"]),
        "externalIntegration": migrated_decision(legacy["externalIntegration"]),
    }
    if converted.get("feature", {}).get("status") != "DRAFT":
        converted["feature"]["status"] = "REVIEW_REQUIRED"
    converted["approval"] = {
        "status": "REVIEW_REQUIRED",
        "approvedBy": None,
        "approvedAt": None,
        "approvedContentSha256": None,
    }
    validate_feature(converted, None)
    return converted


def atomic_write(document: dict[str, Any], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = load_object(args.input)
        migrated = migrate(source)
        atomic_write(migrated, args.output)
    except (OSError, ValueError) as error:
        print(f"FEATURE_SPEC_MIGRATION_VALID: no\nERROR: {error}")
        return 1
    print("FEATURE_SPEC_MIGRATION_VALID: yes")
    print("SOURCE_CHANGED: no")
    print("REVIEW_REQUIRED: yes")
    print(f"OUTPUT: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
