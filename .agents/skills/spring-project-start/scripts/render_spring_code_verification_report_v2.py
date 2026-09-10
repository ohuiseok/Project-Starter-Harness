#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from spring_code_verification_v2 import render_report,validate_apply_readiness,validate_report
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--check",action="store_true");p.add_argument("--require-current-apply-readiness",action="store_true");a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);report_path=a.report.resolve(strict=True);output=a.output.resolve();report=load_object(report_path);validate_report(report,report_path,root)
  if a.require_current_apply_readiness:validate_apply_readiness(report,report_path,root)
  expected=render_report(report)
  if a.check:
   if not output.is_file() or output.read_text()!=expected:raise ValueError("verification report view is stale")
  else:
   if output.exists() or output.is_symlink() or root not in output.parents:raise ValueError("verification view output is unsafe or occupied")
   output.parent.mkdir(parents=True,exist_ok=True);atomic_create(expected.encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_REPORT_V2_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_VERIFICATION_REPORT_V2_VALID: yes");return 0
if __name__=="__main__":sys.exit(main())
