#!/usr/bin/env python3
"""Resolve the next stable feature ID without modifying the target."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_feature_specs import load_object, validate_project


FEATURE_ID = re.compile(r"F(\d{3,})")


def next_feature_id(project_brief: Path, features_directory: Path) -> str:
    project = load_object(project_brief)
    validate_project(project)
    numbers = {
        int(match.group(1))
        for item in project["featureCandidates"]
        if (match := FEATURE_ID.fullmatch(item["id"]))
    }
    if features_directory.exists():
        if not features_directory.is_dir():
            raise ValueError(f"features path is not a directory: {features_directory}")
        for child in features_directory.iterdir():
            match = FEATURE_ID.fullmatch(child.name)
            if match:
                numbers.add(int(match.group(1)))
    value = max(numbers, default=0) + 1
    if value > 999:
        raise ValueError("feature ID space F001-F999 is exhausted")
    return f"F{value:03d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--features-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        feature_id = next_feature_id(args.project_brief, args.features_directory)
    except (OSError, ValueError) as error:
        print(f"NEXT_FEATURE_ID_VALID: no\nERROR: {error}")
        return 1
    print("NEXT_FEATURE_ID_VALID: yes")
    print(f"NEXT_FEATURE_ID: {feature_id}")
    print(f"NEXT_FEATURE_PATH: {args.features_directory / feature_id / 'spec.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
