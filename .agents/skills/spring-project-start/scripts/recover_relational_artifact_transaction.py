#!/usr/bin/env python3
"""Recover one interrupted PREPARED relational artifact transaction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apply_approved_relational_artifacts import recover_transaction


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--target", required=True, type=Path); parser.add_argument("--transaction-id", required=True); args = parser.parse_args()
    try: result = recover_transaction(args.target, args.transaction_id)
    except (OSError, ValueError) as error: print(f"RELATIONAL_ARTIFACT_RECOVERY_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2); print(); print("RELATIONAL_ARTIFACT_RECOVERY_VALID: yes", file=sys.stderr); print("RECOVERY_STATE: RECOVERED", file=sys.stderr); print("DATABASE_OR_CONTAINER_CHANGED: no", file=sys.stderr); return 0


if __name__ == "__main__": sys.exit(main())
