#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_verification_v2 import render_plan,validate_plan
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);plan=load_object(plan_path);validate_plan(plan,plan_path,root)
  if a.view.resolve()!=plan_path.with_suffix(".md") or a.view.read_text()!=render_plan(plan):raise ValueError("verification plan view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_PLAN_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_VERIFICATION_PLAN_V2_VALID: yes\nREADY_FOR_APPROVAL: {'yes' if plan['readyForApproval'] else 'no'}");return 0
if __name__=="__main__":sys.exit(main())
