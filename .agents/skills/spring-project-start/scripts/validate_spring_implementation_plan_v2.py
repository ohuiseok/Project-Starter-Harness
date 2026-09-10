#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from render_spring_implementation_plan_v2 import render
from spring_implementation_plan_v2 import validate
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan=load_object(a.plan);blockers=validate(plan,root)
  if a.view!=a.plan.with_suffix(".md") or not a.view.is_file() or a.view.read_text()!=render(plan,blockers):raise ValueError("implementation plan v2 view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_IMPLEMENTATION_PLAN_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_IMPLEMENTATION_PLAN_V2_VALID: yes\nPLAN_STATUS: {plan['status']}\nADVANCEMENT_READY: {'yes' if plan['status']=='REVIEW_READY' and not blockers else 'no'}\nCODE_DRY_RUN_PREPARATION_AVAILABLE: {'yes' if plan['advancement']['codeDryRun'] else 'no'}");return 0
if __name__=="__main__":sys.exit(main())
