#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from post_apply_verification_v2 import render_plan,validate_plan
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve();plan=load_object(plan_path);result=validate_plan(plan,plan_path,root)
  if not plan["readyForApproval"] or view!=plan_path.with_suffix(".md") or view.read_text()!=render_plan(plan,result) or output.exists() or root not in output.parents:raise ValueError("only the exact ready verification review can be approved")
  if not a.approved_by.strip() or dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00")).utcoffset() is None:raise ValueError("approval identity or time is invalid")
  value={"postApplyVerificationApprovalV2Version":1,"state":"APPROVED","plan":reference(plan_path,root),"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"commandExecution":True,"milestoneCompletion":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"POST_APPLY_VERIFICATION_V2_APPROVED: no\nERROR: {e}");return 1
 print("POST_APPLY_VERIFICATION_V2_APPROVED: yes\nCOMMAND_EXECUTION: authorized\nMILESTONE_COMPLETION: not-authorized");return 0
if __name__=="__main__":sys.exit(main())
