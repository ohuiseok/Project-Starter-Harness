#!/usr/bin/env python3
"""Migrate legacy REUSE/EXTEND metadata without inheriting ambiguous approvals."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from render_design_route import atomic_write
from validate_feature_specs import load_object


def migrate(metadata: dict, report: dict) -> dict:
    if metadata.get("disposition") not in {"REUSE", "EXTEND"}:
        raise ValueError("metadata must be an HTTP API REUSE or EXTEND contract")
    result = copy.deepcopy(metadata)
    result["selectedOperations"] = [item["subjectRef"] for item in result.get("traceability", [])]
    result["compatibilityReviews"] = [
        {
            "reviewId": f"{item['code']}:{item['location']}", "status": "PENDING",
            "reason": "UNKNOWN", "source": "UNKNOWN", "confirmedByUser": False,
        }
        for item in report.get("changes", []) if item.get("level") == "REVIEW"
    ]
    result.pop("acceptedCompatibilityReviews", None)
    result["approval"] = {
        "status": "REVIEW_REQUIRED", "approvedBy": None,
        "approvedAt": None, "approvedContentSha256": None,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("output must differ from input")
        migrated = migrate(load_object(args.input), load_object(args.comparison))
        atomic_write(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", args.output, False)
    except (OSError, ValueError) as error:
        print(f"EXISTING_HTTP_API_MIGRATION_VALID: no\nERROR: {error}")
        return 1
    print("EXISTING_HTTP_API_MIGRATION_VALID: yes")
    print("REVIEW_REQUIRED: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
