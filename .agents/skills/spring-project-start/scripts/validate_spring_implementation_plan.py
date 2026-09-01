#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
from spring_implementation_plan import validate
from validate_feature_specs import load_object

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--plan",required=True,type=Path); parser.add_argument("--target",required=True,type=Path); parser.add_argument("--require-ready",action="store_true"); args=parser.parse_args()
    try: blockers=validate(load_object(args.plan),args.target.resolve(strict=True))
    except (OSError,ValueError,KeyError) as error: print(f"SPRING_IMPLEMENTATION_PLAN_VALID: no\nERROR: {error}"); return 1
    ready=not blockers; print("SPRING_IMPLEMENTATION_PLAN_VALID: yes"); print(f"IMPLEMENTATION_PLAN_READY: {'yes' if ready else 'no'}"); [print(f"BLOCKER: {item}") for item in blockers]; return 1 if args.require_ready and not ready else 0
if __name__=="__main__": sys.exit(main())
