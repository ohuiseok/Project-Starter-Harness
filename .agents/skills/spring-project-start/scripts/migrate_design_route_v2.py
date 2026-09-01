#!/usr/bin/env python3
"""Create a route v2 copy with stable contract identities; never overwrite input."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from render_design_route import atomic_write
from validate_feature_specs import load_object


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "contract"


def migrate(source: dict) -> dict:
    if source.get("routeVersion") != 1:
        raise ValueError("input routeVersion must be 1")
    result = copy.deepcopy(source)
    result["routeVersion"] = 2
    used: set[str] = set()
    for item in result.get("routes", []):
        candidate = slug(item.get("kind", "contract"))
        contract_id = candidate
        number = 2
        while contract_id in used:
            contract_id = f"{candidate}-{number}"
            number += 1
        item["contractId"] = contract_id
        used.add(contract_id)
    result["approval"] = {
        "status": "REVIEW_REQUIRED", "approvedBy": None,
        "approvedAt": None, "approvedContentSha256": None,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("output must differ from input")
        migrated = migrate(load_object(args.input))
        atomic_write(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", args.output, False)
    except (OSError, ValueError) as error:
        print(f"DESIGN_ROUTE_MIGRATION_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_MIGRATION_VALID: yes")
    print("APPROVAL_REQUIRED: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
