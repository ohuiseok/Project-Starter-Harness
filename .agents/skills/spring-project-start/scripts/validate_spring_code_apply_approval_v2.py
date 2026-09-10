#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_apply_v2 import validate_approval
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--approval",required=True,type=Path);p.add_argument("--review",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:validate_approval(a.target.resolve(strict=True),a.approval.resolve(strict=True),a.review.resolve(strict=True))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_APPLY_APPROVAL_V2_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_APPLY_APPROVAL_V2_VALID: yes\nAPPLY_AUTHORIZED: yes");return 0
if __name__=="__main__":sys.exit(main())
