#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,sys
from pathlib import Path
from http_api_spring_mapping import reference
from render_spring_code_dry_run_v2_markdown import render
from spring_code_dry_run_v2 import validate_report
from validate_feature_specs import load_object
def validate_approval(root:Path,path:Path)->dict:
 reference(path,root);receipt=load_object(path)
 if set(receipt)!={"springCodeDryRunV2ApprovalVersion","state","dryRun","view","approvedBy","approvedAt","effects"} or receipt["springCodeDryRunV2ApprovalVersion"]!=1 or receipt["state"]!="APPROVED":raise ValueError("Spring code dry-run v2 approval structure is invalid")
 report_path=root/receipt["dryRun"]["path"];view_path=root/receipt["view"]["path"]
 if reference(report_path,root)!=receipt["dryRun"] or reference(view_path,root)!=receipt["view"]:raise ValueError("approved dry-run or view changed")
 report=load_object(report_path);validate_report(report,root)
 if not report["readyForVerificationApproval"] or view_path!=report_path.with_suffix(".md") or view_path.read_text()!=render(report):raise ValueError("approved dry-run is no longer review-ready")
 if not str(receipt["approvedBy"]).strip():raise ValueError("approvedBy is required")
 datetime.datetime.fromisoformat(receipt["approvedAt"].replace("Z","+00:00"))
 if receipt["effects"]!={"isolatedVerificationAuthorized":True,"sourceChanged":False,"testsExecuted":False,"applyAuthorized":False,"gitCommitOrPush":"NOT_RUN"}:raise ValueError("dry-run approval effects are invalid")
 return receipt
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:validate_approval(a.target.resolve(strict=True),a.approval.resolve(strict=True))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_DRY_RUN_V2_APPROVAL_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_DRY_RUN_V2_APPROVAL_VALID: yes\nISOLATED_VERIFICATION_AUTHORIZED: yes\nAPPLY_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
