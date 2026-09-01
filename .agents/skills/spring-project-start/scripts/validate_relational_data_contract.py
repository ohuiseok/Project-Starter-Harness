#!/usr/bin/env python3
"""Validate a logical relational data contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relational_data_contract import validate_relational_contract
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
        approved, blockers, _ = validate_relational_contract(
            load_object(args.contract), load_object(args.route), args.route, args.target,
            args.contract, load_object(args.feature), load_object(args.profile),
        )
        ready = approved and not blockers
    except (OSError, ValueError) as error:
        print(f"RELATIONAL_DATA_CONTRACT_VALID: no\nERROR: {error}")
        return 1
    print("RELATIONAL_DATA_CONTRACT_VALID: yes")
    print(f"APPROVED: {'yes' if approved else 'no'}")
    print(f"CONTRACT_READY: {'yes' if ready else 'no'}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    return 1 if args.require_ready and not ready else 0


if __name__ == "__main__":
    sys.exit(main())
