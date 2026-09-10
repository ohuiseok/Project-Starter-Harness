#!/usr/bin/env python3
"""Validate a current code renderability v2 report and exact Markdown view."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import reference
from render_spring_code_renderability_v2 import render
from spring_code_renderability_v2 import assess
from validate_feature_specs import load_object
from validate_spring_implementation_plan_v2_approval import validate_approval
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);report_path=a.report.resolve(strict=True);view=a.view.resolve(strict=True);report=load_object(report_path);approval_ref=report["implementationPlanApproval"];approval=root/approval_ref["path"]
  if reference(approval,root)!=approval_ref:raise ValueError("implementation plan approval changed")
  receipt=validate_approval(root,approval);plan=load_object(root/receipt["implementationPlan"]["path"]);expected=assess(plan,root,approval_ref)
  if report!=expected:raise ValueError("renderability report is stale")
  if view!=report_path.with_suffix(".md") or view.read_text()!=render(report):raise ValueError("renderability view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_RENDERABILITY_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_RENDERABILITY_V2_VALID: yes\nBLOCKERS: {len(report['blockers'])}\nCODE_DRY_RUN_READY: {'yes' if report['readyForCodeDryRun'] else 'no'}");return 0
if __name__=="__main__":sys.exit(main())
