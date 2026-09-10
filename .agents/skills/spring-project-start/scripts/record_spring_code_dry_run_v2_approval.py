#!/usr/bin/env python3
"""Record approval of one exact, review-ready Spring code dry-run v2."""
from __future__ import annotations
import argparse,datetime,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from render_spring_code_dry_run_v2_markdown import render
from spring_code_dry_run_v2 import validate_report
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);report_path=a.report.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve();report=load_object(report_path);validate_report(report,root)
  if not report["readyForVerificationApproval"]:raise ValueError("dry-run has blockers")
  if view!=report_path.with_suffix(".md") or view.read_text()!=render(report):raise ValueError("dry-run view is stale")
  if output.exists() or output.is_symlink() or root not in output.parents or output.relative_to(root).parts[0]!="docs":raise ValueError("approval output is unsafe or occupied")
  if not a.approved_by.strip():raise ValueError("approved-by is required")
  datetime.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"));receipt={"springCodeDryRunV2ApprovalVersion":1,"state":"APPROVED","dryRun":reference(report_path,root),"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"isolatedVerificationAuthorized":True,"sourceChanged":False,"testsExecuted":False,"applyAuthorized":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_DRY_RUN_V2_APPROVED: no\nERROR: {e}");return 1
 print("SPRING_CODE_DRY_RUN_V2_APPROVED: yes\nISOLATED_VERIFICATION_AUTHORIZED: yes\nAPPLY_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
