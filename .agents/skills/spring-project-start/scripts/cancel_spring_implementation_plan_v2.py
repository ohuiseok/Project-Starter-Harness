#!/usr/bin/env python3
"""Cancel an exact implementation plan v2 without deleting evidence."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import PII,SECRET,reference
from spring_implementation_plan_v2 import encoded,plan_cancellations,validate
from validate_feature_specs import load_object

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--reason",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);output=a.output.resolve();plan_ref=reference(plan_path,root)
  if a.output.is_symlink() or output.exists() or root not in output.parents or output.relative_to(root).parts[0]!="docs":raise ValueError("cancellation output is unsafe or occupied")
  if plan_cancellations(root,plan_ref):raise ValueError("implementation plan is already cancelled")
  if not a.reason.strip() or SECRET.search(a.reason) or PII.search(a.reason):raise ValueError("cancellation reason is empty or contains sensitive data")
  if validate(load_object(plan_path),root):raise ValueError("only a current implementation plan can be cancelled")
  receipt={"springImplementationPlanV2CancellationVersion":1,"state":"CANCELLED","cancelledPlan":plan_ref,"reason":a.reason.strip(),"effects":{"planDeleted":False,"codeDryRunAuthorized":False,"sourceChanged":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create(encoded(receipt),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_IMPLEMENTATION_PLAN_V2_CANCELLED: no\nERROR: {e}");return 1
 print("SPRING_IMPLEMENTATION_PLAN_V2_CANCELLED: yes\nCODE_DRY_RUN_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
