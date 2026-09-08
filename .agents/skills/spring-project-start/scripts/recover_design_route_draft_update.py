#!/usr/bin/env python3
"""Recover an interrupted immutable design-route draft update."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from spring_milestone_completion import sha, target_path
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-hash", required=True)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        if args.target.is_symlink() or len(args.previous_hash) != 64 or any(character not in "0123456789abcdef" for character in args.previous_hash):
            raise ValueError("target or previous hash is unsafe")
        journal = target_path(root, f".starter-harness/design-route-draft-updates/{args.previous_hash}.json", "route update journal")
        value = load_object(journal)
        required = {"designRouteDraftUpdateVersion", "previous", "next", "view", "answerSummary", "changes", "state"}
        if set(value) != required or value["designRouteDraftUpdateVersion"] != 1 or value["state"] != "PREPARED" or not isinstance(value["answerSummary"], str) or not value["answerSummary"].strip() or not isinstance(value["changes"], list) or not value["changes"]:
            raise ValueError("route update journal is not recoverable")
        for label in ("previous", "next", "view"):
            reference = value[label]
            if not isinstance(reference, dict) or set(reference) != {"path", "sha256"} or not re.fullmatch(r"[a-f0-9]{64}", str(reference["sha256"])):
                raise ValueError(f"{label} reference is invalid")
        if value["previous"]["sha256"] != args.previous_hash:
            raise ValueError("route update journal identity does not match")
        previous = target_path(root, value["previous"]["path"], "previous route")
        if not previous.is_file() or sha(previous) != args.previous_hash:
            raise ValueError("previous route changed; refusing recovery")
        recoverable = []
        for label in ("next", "view"):
            reference = value[label]
            path = target_path(root, reference["path"], f"route update {label}")
            if path.exists() and (not path.is_file() or sha(path) != reference["sha256"]):
                raise ValueError(f"route update {label} drifted; refusing recovery")
            recoverable.append(path)
        for path in reversed(recoverable):
            if path.exists():
                path.unlink()
        journal.unlink()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"DESIGN_ROUTE_DRAFT_RECOVERY_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_DRAFT_RECOVERY_VALID: yes")
    print("UPDATE_STATE: ROLLED_BACK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
