#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_verification_v2 import validate_approval
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--approval",required=True,type=Path);p.add_argument("--plan",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:validate_approval(a.target.resolve(strict=True),a.approval.resolve(strict=True),a.plan.resolve(strict=True))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_PLAN_V2_APPROVAL_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_VERIFICATION_PLAN_V2_APPROVAL_VALID: yes\nVERIFICATION_EXECUTION_AUTHORIZED: yes\nAPPLY_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
