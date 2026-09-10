#!/usr/bin/env python3
"""Validate approval of one exact, current implementation plan v2 and view."""
from __future__ import annotations
import argparse,datetime,sys
from pathlib import Path
from http_api_spring_mapping import reference
from render_spring_implementation_plan_v2 import render
from spring_implementation_plan_v2 import plan_cancellations,validate
from validate_feature_specs import load_object

def validate_approval(root:Path,path:Path)->dict:
 reference(path,root)
 receipt=load_object(path)
 if set(receipt)!={"springImplementationPlanV2ApprovalVersion","state","implementationPlan","view","approvedBy","approvedAt","effects"} or receipt["springImplementationPlanV2ApprovalVersion"]!=2 or receipt["state"]!="APPROVED":raise ValueError("implementation plan v2 approval structure is invalid; create a fresh approval for the active renderer")
 plan_path=root/receipt["implementationPlan"]["path"];view_path=root/receipt["view"]["path"]
 if reference(plan_path,root)!=receipt["implementationPlan"] or reference(view_path,root)!=receipt["view"]:raise ValueError("approved plan or view changed")
 plan=load_object(plan_path);blockers=validate(plan,root)
 if plan["status"]!="REVIEW_READY" or blockers:raise ValueError("approved implementation plan is no longer ready")
 if view_path!=plan_path.with_suffix(".md") or view_path.read_text()!=render(plan,blockers):raise ValueError("approved implementation plan view is stale")
 if plan_cancellations(root,receipt["implementationPlan"]):raise ValueError("approved implementation plan was cancelled")
 if not str(receipt["approvedBy"]).strip():raise ValueError("approvedBy is required")
 datetime.datetime.fromisoformat(receipt["approvedAt"].replace("Z","+00:00"))
 expected={"codeDryRunPreparationAuthorized":True,"isolatedVerificationAuthorized":False,"sourceChanged":False,"testsExecuted":False,"gitCommitOrPush":"NOT_RUN"}
 if receipt["effects"]!=expected:raise ValueError("implementation plan approval effects are invalid")
 return receipt

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:validate_approval(a.target.resolve(strict=True),a.approval.resolve(strict=True))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_IMPLEMENTATION_PLAN_V2_APPROVAL_VALID: no\nERROR: {e}");return 1
 print("SPRING_IMPLEMENTATION_PLAN_V2_APPROVAL_VALID: yes\nCODE_DRY_RUN_PREPARATION_AUTHORIZED: yes\nISOLATED_VERIFICATION_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
