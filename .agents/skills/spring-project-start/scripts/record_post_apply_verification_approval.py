#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from post_apply_verification import validate_plan
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--plan",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--expected-plan-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); plan=a.plan.resolve(strict=True); output=a.output.resolve(strict=False)
  if a.target.is_symlink() or root not in plan.parents or root not in output.parents or output.exists() or sha(plan)!=a.expected_plan_hash: raise ValueError("approval paths or reviewed plan are invalid")
  validate_plan(load_object(plan),plan,root); timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  if not a.approved_by.strip() or timestamp.utcoffset() is None: raise ValueError("approval identity and timezone-aware time are required")
  value={"postApplyVerificationApprovalVersion":1,"approved":True,"planSha256":sha(plan),"target":str(root),"approvedBy":a.approved_by,"approvedAt":a.approved_at}; output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"POST_APPLY_APPROVAL_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("POST_APPLY_APPROVAL_VALID: yes"); return 0
if __name__=="__main__": sys.exit(main())
