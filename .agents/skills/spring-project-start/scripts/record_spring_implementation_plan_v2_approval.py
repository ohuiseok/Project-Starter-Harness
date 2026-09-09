#!/usr/bin/env python3
"""Record explicit approval of an exact current implementation plan v2 view."""
from __future__ import annotations
import argparse,datetime,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from render_spring_implementation_plan_v2 import render
from spring_implementation_plan_v2 import encoded,plan_approvals,plan_cancellations,validate
from validate_feature_specs import load_object

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve()
  if any(path.is_symlink() for path in (a.plan,a.view,a.output)) or any(root not in path.parents for path in (plan_path,view,output)) or output.exists() or output.relative_to(root).parts[0]!="docs":raise ValueError("implementation plan approval paths are unsafe or occupied")
  plan=load_object(plan_path);blockers=validate(plan,root);plan_ref=reference(plan_path,root)
  if plan["status"]!="REVIEW_READY" or blockers:raise ValueError("only a current REVIEW_READY plan can be approved")
  if plan_approvals(root,plan_ref) or plan_cancellations(root,plan_ref):raise ValueError("implementation plan is already approved or cancelled")
  if view!=plan_path.with_suffix(".md") or view.read_text()!=render(plan,blockers):raise ValueError("implementation plan view is stale")
  if not a.approved_by.strip():raise ValueError("approved-by is required")
  datetime.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"));receipt={"springImplementationPlanV2ApprovalVersion":1,"state":"APPROVED","implementationPlan":plan_ref,"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"codeDryRunAuthorized":False,"sourceChanged":False,"testsExecuted":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create(encoded(receipt),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_IMPLEMENTATION_PLAN_V2_APPROVED: no\nERROR: {e}");return 1
 print("SPRING_IMPLEMENTATION_PLAN_V2_APPROVED: yes\nCODE_DRY_RUN_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
