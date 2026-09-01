#!/usr/bin/env python3
"""Validate relational physical design and planning metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relational_physical_contract import validate_physical_contract
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path); parser.add_argument("--physical-model", required=True, type=Path)
    parser.add_argument("--logical-contract", required=True, type=Path); parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path); parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        approved, blockers, _, _ = validate_physical_contract(load_object(args.contract), args.physical_model, args.logical_contract, load_object(args.route), args.route, args.target, load_object(args.feature), load_object(args.profile))
        ready = approved and not blockers
    except (OSError, ValueError) as error:
        print(f"RELATIONAL_PHYSICAL_CONTRACT_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_PHYSICAL_CONTRACT_VALID: yes"); print(f"APPROVED: {'yes' if approved else 'no'}"); print(f"CONTRACT_READY: {'yes' if ready else 'no'}")
    for blocker in blockers: print(f"BLOCKER: {blocker}")
    return 1 if args.require_ready and not ready else 0


if __name__ == "__main__": sys.exit(main())
