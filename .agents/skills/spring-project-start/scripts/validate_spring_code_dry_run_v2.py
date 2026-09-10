#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from render_spring_code_dry_run_v2_markdown import render
from spring_code_dry_run_v2 import validate_report
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);report=load_object(a.report);validate_report(report,root)
  if a.view.resolve()!=a.report.resolve().with_suffix(".md") or a.view.read_text()!=render(report):raise ValueError("Spring code dry-run v2 view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_DRY_RUN_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_DRY_RUN_V2_VALID: yes\nBLOCKERS: {len(report['blockers'])}\nREADY_FOR_VERIFICATION_APPROVAL: {'yes' if report['readyForVerificationApproval'] else 'no'}\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
