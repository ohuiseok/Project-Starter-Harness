#!/usr/bin/env python3
"""Validate HTTP API REUSE/EXTEND evidence and compatibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from existing_http_api_contract import validate_existing_contract
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        approved, blockers, _, report = validate_existing_contract(
            load_object(args.contract), load_object(args.route), args.route, args.target,
            args.contract, load_object(args.feature), load_object(args.profile),
        )
        ready = approved and not blockers
    except (OSError, ValueError) as error:
        print(f"EXISTING_HTTP_API_CONTRACT_VALID: no\nERROR: {error}")
        return 1
    print("EXISTING_HTTP_API_CONTRACT_VALID: yes")
    print(f"APPROVED: {'yes' if approved else 'no'}")
    print(f"CONTRACT_READY: {'yes' if ready else 'no'}")
    print(f"BREAKING_CHANGES: {report['summary']['breaking']}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    return 1 if args.require_ready and not ready else 0


if __name__ == "__main__":
    sys.exit(main())
