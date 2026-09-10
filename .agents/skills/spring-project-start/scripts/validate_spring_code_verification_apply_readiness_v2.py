#!/usr/bin/env python3
"""Recheck only current target evidence before an apply review may be prepared."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_verification_v2 import validate_apply_readiness
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=a.report.resolve(strict=True);validate_apply_readiness(load_object(path),path,root)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_APPLY_READINESS_V2: no\nERROR: {e}");return 1
 print("SPRING_CODE_VERIFICATION_APPLY_READINESS_V2: yes\nHISTORICAL_REPORT_VALID: yes\nCURRENT_TARGET_MATCHES: yes\nREADY_FOR_APPLY_REVIEW: yes");return 0
if __name__=="__main__":sys.exit(main())
