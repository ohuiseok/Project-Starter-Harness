#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from spring_code_verification_v2 import render_plan,validate_plan
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve();plan=load_object(plan_path);validate_plan(plan,plan_path,root)
  if not plan["readyForApproval"] or view!=plan_path.with_suffix(".md") or view.read_text()!=render_plan(plan):raise ValueError("only an exact ready plan view can be approved")
  if output.exists() or root not in output.parents or output.relative_to(root).parts[0]!="docs" or not a.approved_by.strip() or dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00")).utcoffset() is None:raise ValueError("approval output, identity, or time is invalid")
  value={"springCodeVerificationPlanV2ApprovalVersion":1,"state":"APPROVED","plan":reference(plan_path,root),"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"verificationExecutionAuthorized":True,"sourceChanged":False,"applyAuthorized":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_PLAN_V2_APPROVED: no\nERROR: {e}");return 1
 print("SPRING_CODE_VERIFICATION_PLAN_V2_APPROVED: yes\nVERIFICATION_EXECUTION_AUTHORIZED: yes\nAPPLY_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
